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

MAX_INFORMATION_TOOL_CALLS = 8


def validate_answer_question_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    _validate_optional_information_tool_chain(plan, series_mode=False)
    return plan


def validate_series_answer_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    _validate_optional_information_tool_chain(plan, series_mode=True)
    return plan


def _validate_optional_information_tool_chain(plan: AgentActionPlan, *, series_mode: bool) -> None:
    if not plan.tool_calls:
        return
    require_max_tool_calls(plan, MAX_INFORMATION_TOOL_CALLS)
    intent_tag = ToolIntentTag.SERIES_ANSWER if series_mode else ToolIntentTag.ANSWER_QUESTION
    allowed_tool_names = list_tool_names_for_intent(intent_tag)
    require_only_tool_names(
        plan,
        allowed_tool_names,
    )
    validate_tool_call_arguments(plan)
