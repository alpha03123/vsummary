from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.memory.messages import MemoryMessageCompactor
from backend.agent.ports import AgentSessionStore
from backend.agent.schemas.action_plan import AgentTurnResult
from backend.agent.schemas.messages import AgentChatMessage


class AgentGraphSessionRecorder:
    def __init__(
        self,
        *,
        session_store: AgentSessionStore | None = None,
        memory_compactor: MemoryMessageCompactor | None = None,
    ) -> None:
        self._session_store = session_store
        self._memory_compactor = memory_compactor

    @property
    def session_store(self) -> AgentSessionStore | None:
        return self._session_store

    def persist_turn(
        self,
        *,
        session_id: str,
        context: AgentContext,
        user_message: str,
        result: dict[str, object],
        turn_result: AgentTurnResult,
    ) -> None:
        if self._session_store is None:
            return
        messages = self._build_next_memory_messages(
            session_id=session_id,
            user_message=user_message,
            assistant_message=turn_result.assistant_message,
        )
        self._session_store.append_turn(
            session_id=session_id,
            memory_key=session_id,
            context=context,
            messages=messages,
        )

    def clear_session(self, session_id: str) -> None:
        if self._session_store is not None:
            self._session_store.clear_snapshot(session_id)

    def _build_next_memory_messages(
        self,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> list[AgentChatMessage]:
        messages: list[AgentChatMessage] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                messages.extend(
                    AgentChatMessage(role=item.role, content=item.content)
                    for item in snapshot.messages
                )
        messages.extend(
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=assistant_message),
            ]
        )
        if self._memory_compactor is not None:
            return self._memory_compactor.compact_if_needed(messages)
        return messages
