from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolIntentTag, ToolName
from backend.agent.tools import list_tool_names_for_intent
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_max_tool_calls,
    require_only_tool_names,
    require_scope_context,
    validate_tool_call_arguments,
)


def validate_generate_overview_plan(plan: AgentActionPlan) -> AgentActionPlan:
    return _validate_generate_plan(plan, ToolName.GENERATE_OVERVIEW)


def validate_generate_mindmap_plan(plan: AgentActionPlan) -> AgentActionPlan:
    return _validate_generate_plan(plan, ToolName.GENERATE_MINDMAP)


def _validate_generate_plan(plan: AgentActionPlan, expected_tool_name: ToolName) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    require_scope_context(plan)
    if plan.scope_type.value != "video":
        raise AgentPlanError(f"{expected_tool_name.value} 只能在 video 上下文中使用。")
    if not plan.tool_calls:
        return plan
    require_max_tool_calls(plan, 2)
    intent_tag = (
        ToolIntentTag.GENERATE_OVERVIEW
        if expected_tool_name == ToolName.GENERATE_OVERVIEW
        else ToolIntentTag.GENERATE_MINDMAP
    )
    allowed_tool_names = list_tool_names_for_intent(intent_tag)
    require_only_tool_names(plan, allowed_tool_names)
    validate_tool_call_arguments(plan)
    return plan
