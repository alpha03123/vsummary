from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import AgentContextLoader, AgentSessionStore
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.memory.dialog_history import render_dialog_history


def load_runtime_context(
    *,
    context_loader: AgentContextLoader,
    memory_store: AgentMemoryStore,
    session_id: str,
    context_override: AgentContext | None,
    session_store: AgentSessionStore | None = None,
) -> tuple[AgentContext, str, list[AgentChatMessage]]:
    base_context = context_loader.load(session_id)
    snapshot_context = None
    if session_store is not None:
        snapshot = session_store.get_snapshot(session_id)
        if snapshot is not None:
            snapshot_context = snapshot.context
    context = merge_context(base_context, snapshot_context)
    context = merge_context(context, context_override)
    memory_key = build_memory_key(context, session_id)
    history = memory_store.get_messages(memory_key)
    return attach_dialog_history(context, history), memory_key, history


def merge_context(base_context: AgentContext, context_override: AgentContext | None) -> AgentContext:
    if context_override is None:
        return base_context

    override_payload = context_override.model_dump(exclude_unset=True)
    override_payload.pop("session_id", None)
    return base_context.model_copy(update=override_payload)


def build_memory_key(context: AgentContext, session_id: str) -> str:
    del context
    return session_id


def attach_dialog_history(
    context: AgentContext,
    history: list[AgentChatMessage],
) -> AgentContext:
    return context.model_copy(update={"dialog_history": render_dialog_history(history)})
