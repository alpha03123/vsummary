from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from backend.agent.schemas.messages import AgentChatMessage


class AgentMemoryStore(Protocol):
    def get_messages(self, session_id: str) -> list[AgentChatMessage]:
        ...

    def append_messages(self, session_id: str, messages: list[AgentChatMessage]) -> None:
        ...

    def replace_messages(self, session_id: str, messages: list[AgentChatMessage]) -> None:
        ...

    def clear_messages(self, session_id: str) -> None:
        ...


class InMemoryAgentMemoryStore:
    def __init__(self) -> None:
        self._messages: dict[str, list[AgentChatMessage]] = defaultdict(list)

    def get_messages(self, session_id: str) -> list[AgentChatMessage]:
        return list(self._messages.get(session_id, []))

    def append_messages(self, session_id: str, messages: list[AgentChatMessage]) -> None:
        self._messages[session_id].extend(messages)

    def replace_messages(self, session_id: str, messages: list[AgentChatMessage]) -> None:
        self._messages[session_id] = list(messages)

    def clear_messages(self, session_id: str) -> None:
        self._messages.pop(session_id, None)
