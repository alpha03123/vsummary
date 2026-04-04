from __future__ import annotations

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.validation.errors import AgentPlanError


def validate_out_of_scope_plan(plan: AgentActionPlan) -> AgentActionPlan:
    if not plan.out_of_scope_reason.strip():
        raise AgentPlanError("out_of_scope 必须提供 out_of_scope_reason。")
    if plan.tool_calls:
        raise AgentPlanError("out_of_scope 不应包含工具调用。")
    return plan
