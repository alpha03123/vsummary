from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolName
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_only_tool_names,
    require_scope_not_library,
    require_tool_calls,
    validate_tool_call_arguments,
)


def validate_generate_overview_plan(plan: AgentActionPlan) -> AgentActionPlan:
    return _validate_generate_plan(plan, ToolName.GENERATE_OVERVIEW)


def validate_generate_mindmap_plan(plan: AgentActionPlan) -> AgentActionPlan:
    return _validate_generate_plan(plan, ToolName.GENERATE_MINDMAP)


def _validate_generate_plan(plan: AgentActionPlan, expected_tool_name: ToolName) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    require_scope_not_library(plan)
    require_tool_calls(plan)
    require_only_tool_names(plan, {expected_tool_name})
    validate_tool_call_arguments(plan)
    return plan
