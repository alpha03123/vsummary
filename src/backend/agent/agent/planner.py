from __future__ import annotations

from pydantic import TypeAdapter

from backend.agent.agent.prompt import build_agent_planner_prompt
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan, PlannerActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolCall
from backend.agent.validation.plan import validate_action_plan


def extract_action_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
) -> AgentActionPlan:
    history = memory_store.get_messages(session_id)
    messages = [
        AgentChatMessage(role="system", content=build_agent_planner_prompt(context)),
        *history,
        AgentChatMessage(role="user", content=user_message),
    ]
    planner_plan = gateway.create_structured_completion(messages, PlannerActionPlan)
    plan = _convert_planner_plan(planner_plan)
    return validate_action_plan(plan)


def _convert_planner_plan(planner_plan: PlannerActionPlan) -> AgentActionPlan:
    tool_call_adapter = TypeAdapter(ToolCall)
    tool_calls = [
        tool_call_adapter.validate_python(
            call.model_dump(exclude_none=True),
        )
        for call in planner_plan.tool_calls
    ]
    return AgentActionPlan(
        intent_type=planner_plan.intent_type,
        scope_type=planner_plan.scope_type,
        assistant_message=planner_plan.assistant_message,
        tool_calls=tool_calls,
        reason=planner_plan.reason,
        out_of_scope_reason=planner_plan.out_of_scope_reason,
    )
