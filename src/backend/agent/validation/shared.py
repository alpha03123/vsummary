from __future__ import annotations

from collections.abc import Iterable

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolName, TranscriptLookupCall, VideoSeekCall
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
