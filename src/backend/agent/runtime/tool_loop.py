from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.ports import AgentToolExecutor
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import (
    SaveNoteCall,
    ToolCall,
    ToolExecutionResult,
    ToolName,
)
from backend.agent.tools import tool_is_concurrency_safe


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
    return _apply_series_listing_stage(next_context, result)


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
