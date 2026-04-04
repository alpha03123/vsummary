from __future__ import annotations

from collections.abc import Callable

from backend.agent.schemas.action_plan import AgentActionPlan, IntentType
from backend.agent.validation.answer import (
    validate_answer_question_plan,
    validate_series_answer_plan,
)
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.generate import (
    validate_generate_mindmap_plan,
    validate_generate_overview_plan,
)
from backend.agent.validation.open_tool import validate_open_tool_plan
from backend.agent.validation.out_of_scope import validate_out_of_scope_plan
from backend.agent.validation.seek_video import validate_seek_video_plan


PlanValidator = Callable[[AgentActionPlan], AgentActionPlan]


PLAN_VALIDATORS: dict[IntentType, PlanValidator] = {
    IntentType.ANSWER_QUESTION: validate_answer_question_plan,
    IntentType.OPEN_TOOL: validate_open_tool_plan,
    IntentType.SEEK_VIDEO: validate_seek_video_plan,
    IntentType.GENERATE_OVERVIEW: validate_generate_overview_plan,
    IntentType.GENERATE_MINDMAP: validate_generate_mindmap_plan,
    IntentType.SERIES_ANSWER: validate_series_answer_plan,
    IntentType.OUT_OF_SCOPE: validate_out_of_scope_plan,
}


def validate_action_plan(plan: AgentActionPlan) -> AgentActionPlan:
    validator = PLAN_VALIDATORS.get(plan.intent_type)
    if validator is None:
        raise AgentPlanError(f"Unsupported intent_type: {plan.intent_type.value}")
    return validator(plan)
