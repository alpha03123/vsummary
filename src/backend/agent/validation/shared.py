from __future__ import annotations

from collections.abc import Iterable

from backend.agent.tools import get_tool_definition, tool_requires_video_id
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import (
    GetVideoSummaryCall,
    GetVideoTranscriptCall,
    GetVideoToolsCall,
    ListSeriesVideosCall,
    SaveNoteCall,
    ToolName,
    VideoSeekCall,
)
from backend.agent.validation.errors import AgentPlanError


def require_empty_out_of_scope_reason(plan: AgentActionPlan) -> None:
    if plan.out_of_scope_reason.strip():
        raise AgentPlanError("非 out_of_scope 场景不应填写 out_of_scope_reason。")


def require_scope_context(plan: AgentActionPlan) -> None:
    if plan.scope_type.value not in {"series", "video"}:
        raise AgentPlanError("当前意图要求 scope_type 必须是 series 或 video。")
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
        if isinstance(call, VideoSeekCall) and call.match_end_seconds is not None and call.match_end_seconds < call.seek_seconds:
            raise AgentPlanError("video_seek 的 match_end_seconds 不能早于 seek_seconds。")
        if isinstance(call, ListSeriesVideosCall) and call.series_id is not None and not call.series_id.strip():
            raise AgentPlanError("list_series_videos 的 series_id 不能为空字符串。")
        if isinstance(call, SaveNoteCall):
            if not call.note_title.strip():
                raise AgentPlanError("save_note 的 note_title 不能为空。")
            if not call.note_content.strip():
                raise AgentPlanError("save_note 的 note_content 不能为空。")
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
