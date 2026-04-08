from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.note_drafter import draft_video_note
from backend.agent.runtime.tool_loop import (
    build_save_note_call,
    extract_latest_summary_result,
    extract_latest_transcript_result,
)
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import GetVideoTranscriptCall, ToolExecutionResult, ToolName


def build_save_note_followup_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
    last_tool_plan: AgentActionPlan | None,
) -> AgentActionPlan | None:
    if last_tool_plan is None or last_tool_plan.intent_type.value != "save_note":
        return None
    if any(result.tool_name == ToolName.SAVE_NOTE for result in observed_tool_results):
        return None

    summary_result = extract_latest_summary_result(observed_tool_results)
    transcript_result = extract_latest_transcript_result(observed_tool_results)

    if summary_result is None and transcript_result is None:
        return None

    if summary_result is not None and summary_result.status == "ok":
        draft = draft_video_note(
            gateway=gateway,
            user_message=user_message,
            evidence_result=summary_result,
        )
        return AgentActionPlan(
            intent_type="save_note",
            scope_type="video",
            tool_calls=[build_save_note_call(draft.note_title, draft.note_content)],
            reason=draft.reason or "已经根据视频概况整理出可直接保存的笔记。",
        )

    if transcript_result is None and context.series_id and context.video_id:
        return AgentActionPlan(
            intent_type="save_note",
            scope_type="video",
            tool_calls=[
                GetVideoTranscriptCall(
                    tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                    series_id=context.series_id,
                    video_id=context.video_id,
                )
            ],
            reason="当前没有可直接使用的概况，改为读取 transcript 后再整理笔记。",
        )

    if transcript_result is not None and transcript_result.status == "ok":
        draft = draft_video_note(
            gateway=gateway,
            user_message=user_message,
            evidence_result=transcript_result,
        )
        return AgentActionPlan(
            intent_type="save_note",
            scope_type="video",
            tool_calls=[build_save_note_call(draft.note_title, draft.note_content)],
            reason=draft.reason or "已经根据视频转写整理出可直接保存的笔记。",
        )

    return None
