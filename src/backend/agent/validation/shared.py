from __future__ import annotations

from collections.abc import Iterable

from backend.agent.tools import get_tool_definition, tool_requires_video_id
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import (
    AddSeriesCandidatesCall,
    ClearSeriesCandidatesCall,
    GetVideoSummaryCall,
    GetVideoTranscriptCall,
    GetVideoToolsCall,
    ListSeriesVideosCall,
    RemoveSeriesCandidatesCall,
    ReplaceSeriesCandidatesCall,
    ToolName,
    VideoSeekCall,
    ViewSeriesCandidatesCall,
)
from backend.agent.validation.errors import AgentPlanError


def require_empty_out_of_scope_reason(plan: AgentActionPlan) -> None:
    if plan.out_of_scope_reason.strip():
        raise AgentPlanError("非 out_of_scope 场景不应填写 out_of_scope_reason。")


def require_scope_context(plan: AgentActionPlan) -> None:
    if plan.scope_type.value not in {"series", "video"}:
        raise AgentPlanError("当前意图要求 scope_type 必须是 series 或 video。")


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


def validate_batch_tool_usage(plan: AgentActionPlan) -> None:
    tool_name_counts: dict[ToolName, int] = {}
    for call in plan.tool_calls:
        tool_name_counts[call.tool_name] = tool_name_counts.get(call.tool_name, 0) + 1

    for tool_name, count in tool_name_counts.items():
        if count <= 1:
            continue
        tool_definition = get_tool_definition(tool_name)
        if tool_definition.batch_tag:
            continue
        raise AgentPlanError(
            f"{tool_name.value} 未标记批量标签，不能在同一轮重复调用。"
        )


def validate_tool_call_arguments(plan: AgentActionPlan) -> None:
    for call in plan.tool_calls:
        if isinstance(call, VideoSeekCall) and call.seek_seconds < 0:
            raise AgentPlanError("video_seek 的 seek_seconds 不能为负数。")
        if isinstance(call, ListSeriesVideosCall) and call.series_id is not None and not call.series_id.strip():
            raise AgentPlanError("list_series_videos 的 series_id 不能为空字符串。")
        if isinstance(call, ViewSeriesCandidatesCall):
            continue
        if isinstance(call, AddSeriesCandidatesCall | RemoveSeriesCandidatesCall | ReplaceSeriesCandidatesCall):
            if not call.video_ids:
                raise AgentPlanError(f"{call.tool_name.value} 至少需要一个 video_id。")
            for video_id in call.video_ids:
                if not isinstance(video_id, str) or not video_id.strip():
                    raise AgentPlanError(f"{call.tool_name.value} 的 video_ids 不能包含空值。")
                if _looks_like_unresolved_placeholder(video_id):
                    raise AgentPlanError(f"{call.tool_name.value} 的 video_ids 不能使用未解析占位值。")
        if isinstance(call, ClearSeriesCandidatesCall):
            continue
        if tool_requires_video_id(call.tool_name):
            _validate_video_target_arguments(call)


def _looks_like_unresolved_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("*pending_") or "pending_from_" in normalized


def _validate_video_target_arguments(
    call: GetVideoSummaryCall | GetVideoToolsCall | GetVideoTranscriptCall,
) -> None:
    tool_name = get_tool_definition(call.tool_name).name.value
    if call.series_id is not None and not call.series_id.strip():
        raise AgentPlanError(f"{tool_name} 的 series_id 不能为空字符串。")
    if call.video_id is not None and not call.video_id.strip():
        raise AgentPlanError(f"{tool_name} 的 video_id 不能为空字符串。")
    if call.video_id is not None and _looks_like_unresolved_placeholder(call.video_id):
        raise AgentPlanError(f"{tool_name} 的 video_id 不能使用未解析占位值。")
