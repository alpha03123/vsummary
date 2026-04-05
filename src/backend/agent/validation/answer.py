from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolName
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_max_tool_calls,
    require_only_tool_names,
    validate_tool_call_arguments,
)


def validate_answer_question_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    _validate_optional_information_tool_chain(plan)
    return plan


def validate_series_answer_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    _validate_optional_information_tool_chain(plan)
    return plan


def _validate_optional_information_tool_chain(plan: AgentActionPlan) -> None:
    if not plan.tool_calls:
        return
    require_max_tool_calls(plan, 3)
    require_only_tool_names(
        plan,
        {
            ToolName.LIST_SERIES_VIDEOS,
            ToolName.GET_VIDEO_SUMMARY,
            ToolName.GET_VIDEO_TOOLS,
        },
    )
    validate_tool_call_arguments(plan)
