from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolIntentTag
from backend.agent.tools import list_tool_names_for_intent
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_only_tool_names,
    validate_tool_call_arguments,
)


def validate_open_tool_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    if not plan.tool_calls:
        return plan
    require_only_tool_names(
        plan,
        list_tool_names_for_intent(ToolIntentTag.OPEN_TOOL),
    )
    validate_tool_call_arguments(plan)
    return plan
