from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolIntentTag
from backend.agent.tools import list_tool_names_for_intent
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_only_tool_names,
    require_scope_context,
    validate_tool_call_arguments,
)


def validate_seek_video_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    require_scope_context(plan)
    if not plan.tool_calls:
        return plan
    require_only_tool_names(
        plan,
        list_tool_names_for_intent(ToolIntentTag.SEEK_VIDEO),
    )
    validate_tool_call_arguments(plan)
    return plan
