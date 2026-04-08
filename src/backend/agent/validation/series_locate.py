from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolIntentTag
from backend.agent.tools import list_tool_names_for_intent
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_max_tool_calls,
    require_only_tool_names,
    validate_tool_call_arguments,
)


MAX_SERIES_LOCATE_TOOL_CALLS = 8


def validate_series_locate_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    if not plan.tool_calls:
        return plan
    require_max_tool_calls(plan, MAX_SERIES_LOCATE_TOOL_CALLS)
    require_only_tool_names(
        plan,
        list_tool_names_for_intent(ToolIntentTag.SERIES_LOCATE),
    )
    validate_tool_call_arguments(plan)
    return plan
