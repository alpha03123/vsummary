from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolName
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_only_tool_names,
    require_tool_calls,
    validate_tool_call_arguments,
)


def validate_open_tool_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    require_tool_calls(plan)
    require_only_tool_names(
        plan,
        {
            ToolName.OPEN_SERIES_HOME,
            ToolName.OPEN_OVERVIEW,
            ToolName.OPEN_NOTES,
            ToolName.OPEN_VIDEO,
            ToolName.SAVE_NOTE,
        },
    )
    validate_tool_call_arguments(plan)
    return plan
