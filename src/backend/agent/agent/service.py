from __future__ import annotations

from backend.agent.agent.planner import extract_action_plan
from backend.agent.agent.responder import generate_assistant_message
from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore, InMemoryAgentMemoryStore
from backend.agent.ports import AgentContextLoader, AgentToolExecutor, ChatGateway
from backend.agent.schemas.action_plan import AgentTurnResult
from backend.agent.schemas.messages import AgentChatMessage


class AgentService:
    def __init__(
        self,
        gateway: ChatGateway,
        context_loader: AgentContextLoader,
        memory_store: AgentMemoryStore | None = None,
        tool_executor: AgentToolExecutor | None = None,
    ) -> None:
        self._gateway = gateway
        self._context_loader = context_loader
        self._memory_store = memory_store or InMemoryAgentMemoryStore()
        self._tool_executor = tool_executor or RegistryAgentToolExecutor(registry={})

    def run(self, session_id: str, user_message: str) -> AgentTurnResult:
        return self.run_with_context(session_id=session_id, user_message=user_message, context_override=None)

    def run_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override: AgentContext | None,
    ) -> AgentTurnResult:
        base_context = self._context_loader.load(session_id)
        context = _merge_context(base_context, context_override)
        memory_key = _build_memory_key(context, session_id)
        context = _attach_recent_messages(context, self._memory_store.get_messages(memory_key))
        plan = extract_action_plan(
            gateway=self._gateway,
            context=context,
            memory_store=self._memory_store,
            session_id=memory_key,
            user_message=user_message,
        )
        tool_results = self._tool_executor.execute(plan, context)
        assistant_message = generate_assistant_message(
            gateway=self._gateway,
            context=context,
            memory_store=self._memory_store,
            session_id=memory_key,
            user_message=user_message,
            plan=plan,
            tool_results=tool_results,
        )
        self._memory_store.append_messages(
            memory_key,
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=assistant_message),
            ],
        )
        return AgentTurnResult(
            assistant_message=assistant_message,
            plan=plan,
            tool_results=tool_results,
        )


def _merge_context(base_context: AgentContext, context_override: AgentContext | None) -> AgentContext:
    if context_override is None:
        return base_context

    override_payload = context_override.model_dump(exclude_unset=True)
    override_payload.pop("session_id", None)
    return base_context.model_copy(update=override_payload)


def _build_memory_key(context: AgentContext, session_id: str) -> str:
    if context.scope_type == "library" or not context.series_id:
        return "library"
    return f"series|{context.series_id}"


def _attach_recent_messages(context: AgentContext, history: list[AgentChatMessage]) -> AgentContext:
    recent_messages = [message.content for message in history[-6:]]
    return context.model_copy(update={"recent_messages": recent_messages})
