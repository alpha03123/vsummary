from __future__ import annotations

from backend.agent.agent.prompt import build_agent_planner_prompt
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.messages import AgentChatMessage
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
    plan = gateway.create_structured_completion(messages, AgentActionPlan)
    return validate_action_plan(plan)
