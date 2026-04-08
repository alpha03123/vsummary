from __future__ import annotations

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.schemas.action_plan import AgentActionPlan, IntentType, ScopeType
from backend.agent.schemas.tool_calls import GetVideoSummaryCall, ToolExecutionResult, ToolName


def build_followup_plan(
    *,
    context: AgentContext,
    observed_tool_results: list[ToolExecutionResult],
    last_tool_plan: AgentActionPlan | None,
) -> AgentActionPlan | None:
    if last_tool_plan is None:
        return None
    if last_tool_plan.intent_type != IntentType.SERIES_ANSWER:
        return None
    if context.scope_type != ScopeType.SERIES.value:
        return None
    if context.inspection_stage != InspectionStage.VIDEO_INSPECTION:
        return None
    if _has_series_read_results(observed_tool_results):
        return None

    listed_video_ids = _extract_latest_listed_video_ids(observed_tool_results)
    if not listed_video_ids:
        return None

    return AgentActionPlan(
        intent_type=IntentType.SERIES_ANSWER,
        scope_type=ScopeType.SERIES,
        tool_calls=[
            GetVideoSummaryCall(
                tool_name=ToolName.GET_VIDEO_SUMMARY,
                series_id=context.series_id,
                video_id=video_id,
            )
            for video_id in listed_video_ids
        ],
        reason="系列问答默认先批量读取系列视频概况，再基于证据汇总回答。",
    )


def _has_series_read_results(observed_tool_results: list[ToolExecutionResult]) -> bool:
    return any(
        result.tool_name in {
            ToolName.GET_VIDEO_SUMMARY,
            ToolName.GET_VIDEO_TOOLS,
            ToolName.GET_VIDEO_TRANSCRIPT,
        }
        for result in observed_tool_results
    )


def _extract_latest_listed_video_ids(observed_tool_results: list[ToolExecutionResult]) -> list[str]:
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
