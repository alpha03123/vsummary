from __future__ import annotations

from collections.abc import Iterable

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import (
    GetVideoSummaryCall,
    GetVideoToolsCall,
    ListSeriesVideosCall,
    ToolName,
    TranscriptLookupCall,
    VideoSeekCall,
)
from backend.agent.validation.errors import AgentPlanError


def require_empty_out_of_scope_reason(plan: AgentActionPlan) -> None:
    if plan.out_of_scope_reason.strip():
        raise AgentPlanError("非 out_of_scope 场景不应填写 out_of_scope_reason。")


def require_scope_not_library(plan: AgentActionPlan) -> None:
    if plan.scope_type.value == "library":
        raise AgentPlanError("当前意图要求 scope_type 至少是 series 或 video。")


def require_tool_calls(plan: AgentActionPlan) -> None:
    if not plan.tool_calls:
        raise AgentPlanError("当前意图至少需要一个工具调用。")


def require_max_tool_calls(plan: AgentActionPlan, maximum: int) -> None:
    if len(plan.tool_calls) > maximum:
        raise AgentPlanError(f"{plan.intent_type.value} 最多允许 {maximum} 个工具调用。")


def require_only_tool_names(plan: AgentActionPlan, allowed_tool_names: Iterable[ToolName]) -> None:
    allowed = set(allowed_tool_names)
    for call in plan.tool_calls:
        if call.tool_name not in allowed:
            raise AgentPlanError(
                f"{plan.intent_type.value} 不允许工具 {call.tool_name.value}。"
            )


def validate_tool_call_arguments(plan: AgentActionPlan) -> None:
    for call in plan.tool_calls:
        if isinstance(call, VideoSeekCall) and call.seek_seconds < 0:
            raise AgentPlanError("video_seek 的 seek_seconds 不能为负数。")
        if isinstance(call, TranscriptLookupCall) and not call.query.strip():
            raise AgentPlanError("transcript_lookup 的 query 不能为空。")
        if isinstance(call, ListSeriesVideosCall) and call.series_id is not None and not call.series_id.strip():
            raise AgentPlanError("list_series_videos 的 series_id 不能为空字符串。")
        if isinstance(call, GetVideoSummaryCall):
            if call.series_id is not None and not call.series_id.strip():
                raise AgentPlanError("get_video_summary 的 series_id 不能为空字符串。")
            if call.video_id is not None and not call.video_id.strip():
                raise AgentPlanError("get_video_summary 的 video_id 不能为空字符串。")
            if call.video_id is not None and _looks_like_unresolved_placeholder(call.video_id):
                raise AgentPlanError("get_video_summary 的 video_id 不能使用未解析占位值。")
        if isinstance(call, GetVideoToolsCall):
            if call.series_id is not None and not call.series_id.strip():
                raise AgentPlanError("get_video_tools 的 series_id 不能为空字符串。")
            if call.video_id is not None and not call.video_id.strip():
                raise AgentPlanError("get_video_tools 的 video_id 不能为空字符串。")
            if call.video_id is not None and _looks_like_unresolved_placeholder(call.video_id):
                raise AgentPlanError("get_video_tools 的 video_id 不能使用未解析占位值。")


def _looks_like_unresolved_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("*pending_") or "pending_from_" in normalized
