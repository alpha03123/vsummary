from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolIntentTag
from backend.agent.tools import list_tool_names_for_intent
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.shared import (
    require_empty_out_of_scope_reason,
    require_max_tool_calls,
    require_only_tool_names,
    require_scope_context,
    validate_tool_call_arguments,
)


def validate_save_note_plan(plan: AgentActionPlan) -> AgentActionPlan:
    require_empty_out_of_scope_reason(plan)
    require_scope_context(plan)
    if plan.scope_type.value != "video":
        raise AgentPlanError("save_note 只能在 video 上下文中使用。")
    if not plan.tool_calls:
        return plan
    require_max_tool_calls(plan, 3)
    require_only_tool_names(
        plan,
        list_tool_names_for_intent(ToolIntentTag.SAVE_NOTE),
    )
    validate_tool_call_arguments(plan)
    return plan
