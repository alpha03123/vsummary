from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.shared import require_empty_out_of_scope_reason


def validate_answer_question_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    if plan.tool_calls:
        raise AgentPlanError("answer_question 不应包含工具调用。")
    return plan


def validate_series_answer_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    if plan.tool_calls:
        raise AgentPlanError("series_answer 不应包含工具调用。")
    return plan
