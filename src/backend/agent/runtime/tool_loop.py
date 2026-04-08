from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.agent.memory.context import AgentContext, CandidateBufferEntry, InspectionStage
from backend.agent.ports import AgentToolExecutor
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import (
    SaveNoteCall,
    ToolCall,
    ToolEffectTag,
    ToolExecutionResult,
    ToolName,
)
from backend.agent.tools import tool_has_effect, tool_is_concurrency_safe


def execute_tool_batch(
    *,
    tool_executor: AgentToolExecutor,
    calls: list[ToolCall],
    context: AgentContext,
) -> list[ToolExecutionResult]:
    if len(calls) <= 1 or not all(tool_is_concurrency_safe(call.tool_name) for call in calls):
        return [
            tool_executor.execute_call(call, context)
            for call in calls
        ]
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [
            executor.submit(tool_executor.execute_call, call, context)
            for call in calls
        ]
        return [future.result() for future in futures]


def partition_tool_calls(calls: list[ToolCall]) -> list[list[ToolCall]]:
    batches: list[list[ToolCall]] = []
    for call in calls:
        if tool_is_concurrency_safe(call.tool_name) and batches and all(
            tool_is_concurrency_safe(item.tool_name)
            for item in batches[-1]
        ):
            batches[-1].append(call)
            continue
        batches.append([call])
    return batches


def apply_tool_result_to_context(context: AgentContext, result: ToolExecutionResult) -> AgentContext:
    payload = result.payload
    next_context = _apply_selected_tool_payload(context, payload)
    next_context = _apply_series_listing_stage(next_context, result)
    if tool_has_effect(result.tool_name, ToolEffectTag.APPLY_CANDIDATE_BUFFER_PAYLOAD):
        return _apply_candidate_buffer_payload(next_context, payload)
    if tool_has_effect(result.tool_name, ToolEffectTag.MARK_VIDEO_INSPECTED):
        return _mark_video_as_inspected(next_context, payload.get("video_id"))
    return next_context
def finalize_context_after_turn(
    context: AgentContext,
    tool_results: list[ToolExecutionResult],
) -> AgentContext:
    if context.scope_type != "series":
        return context
    if context.inspection_stage != InspectionStage.VIDEO_INSPECTION:
        return context
    if not any(
        result.tool_name in {
            ToolName.GET_VIDEO_SUMMARY,
            ToolName.GET_VIDEO_TRANSCRIPT,
            ToolName.GET_VIDEO_TOOLS,
        }
        for result in tool_results
    ):
        return context
    return context.model_copy(
        update={
            "inspection_stage": InspectionStage.ANSWER_READY,
            "candidate_buffer": [],
        }
    )


def extract_latest_transcript_result(
    observed_tool_results: list[ToolExecutionResult],
) -> ToolExecutionResult | None:
    for result in reversed(observed_tool_results):
        if result.tool_name == ToolName.GET_VIDEO_TRANSCRIPT and result.status == "ok":
            return result
    return None


def extract_latest_summary_result(
    observed_tool_results: list[ToolExecutionResult],
) -> ToolExecutionResult | None:
    for result in reversed(observed_tool_results):
        if result.tool_name == ToolName.GET_VIDEO_SUMMARY:
            return result
    return None


def extract_latest_listed_video_ids(
    observed_tool_results: list[ToolExecutionResult],
) -> list[str]:
    for result in reversed(observed_tool_results):
        if result.tool_name != ToolName.LIST_SERIES_VIDEOS or result.status != "ok":
            continue
        videos = result.payload.get("videos")
        if not isinstance(videos, list):
            return []
        return [
            str(video.get("video_id", "")).strip()
            for video in videos
            if isinstance(video, dict) and str(video.get("video_id", "")).strip()
        ]
    return []


def extract_series_summary_results(
    observed_tool_results: list[ToolExecutionResult],
) -> list[ToolExecutionResult]:
    return [
        result
        for result in observed_tool_results
        if result.tool_name == ToolName.GET_VIDEO_SUMMARY and result.status == "ok"
    ]


def extract_series_transcript_results(
    observed_tool_results: list[ToolExecutionResult],
) -> list[ToolExecutionResult]:
    return [
        result
        for result in observed_tool_results
        if result.tool_name == ToolName.GET_VIDEO_TRANSCRIPT and result.status == "ok"
    ]


def build_save_note_call(note_title: str, note_content: str) -> SaveNoteCall:
    resolved_title = note_title.strip()
    resolved_content = note_content.strip()
    if not resolved_title:
        raise RuntimeError("save_note 缺少 note_title。")
    if not resolved_content:
        raise RuntimeError("save_note 缺少 note_content。")
    return SaveNoteCall(
        tool_name=ToolName.SAVE_NOTE,
        note_title=resolved_title,
        note_content=resolved_content,
    )


def _apply_selected_tool_payload(context: AgentContext, payload: dict[str, object]) -> AgentContext:
    selected_tool = payload.get("selected_tool")
    if not isinstance(selected_tool, str) or not selected_tool.strip():
        return context
    return context.model_copy(update={"selected_tool": selected_tool.strip()})


def _apply_series_listing_stage(context: AgentContext, result: ToolExecutionResult) -> AgentContext:
    if result.tool_name != ToolName.LIST_SERIES_VIDEOS:
        return context
    if context.scope_type != "series":
        return context
    videos = result.payload.get("videos")
    if not isinstance(videos, list) or not videos:
        return context
    return context.model_copy(update={"inspection_stage": InspectionStage.VIDEO_INSPECTION})


def _apply_candidate_buffer_payload(context: AgentContext, payload: dict[str, object]) -> AgentContext:
    raw_buffer = payload.get("candidate_buffer")
    next_buffer = context.candidate_buffer
    if isinstance(raw_buffer, list):
        next_buffer = [
            CandidateBufferEntry.model_validate(item)
            for item in raw_buffer
            if isinstance(item, dict)
        ]
    return context.model_copy(update={"candidate_buffer": next_buffer})


def _mark_video_as_inspected(context: AgentContext, video_id: object) -> AgentContext:
    if not isinstance(video_id, str) or not video_id.strip():
        return context
    normalized_video_id = video_id.strip()
    if normalized_video_id in context.inspected_video_ids:
        return context
    return context.model_copy(
        update={
            "inspected_video_ids": [*context.inspected_video_ids, normalized_video_id],
        }
    )
