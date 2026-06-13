from __future__ import annotations

from math import ceil

from backend.agent.context.semantic_compactor import compact_conversation_messages, render_compacted_payload
from backend.agent.ports import ChatGateway
from backend.agent.schemas.messages import AgentChatMessage


def render_memory_messages(messages: list[AgentChatMessage]) -> str:
    lines = [
        f"{message.role}: {message.content.strip()}"
        for message in messages
        if isinstance(message.content, str) and message.content.strip()
    ]
    return "\n".join(lines).strip()


def estimate_memory_message_tokens(messages: list[AgentChatMessage]) -> int:
    text = render_memory_messages(messages)
    if not text:
        return 0
    return max(1, ceil(len(text.encode("utf-8")) / 3))


class MemoryMessageCompactor:
    def __init__(
        self,
        *,
        gateway: ChatGateway,
        context_window_tokens: int,
        compression_ratio: float = 0.90,
    ) -> None:
        self._gateway = gateway
        self._context_window_tokens = context_window_tokens
        self._compression_ratio = compression_ratio
        self._compression_threshold_tokens = int(context_window_tokens * compression_ratio)

    @property
    def compression_threshold_tokens(self) -> int:
        return self._compression_threshold_tokens

    def compact_messages(self, messages: list[AgentChatMessage]) -> list[AgentChatMessage]:
        payload = compact_conversation_messages(
            gateway=self._gateway,
            messages=messages,
        )
        return [AgentChatMessage(role="system", content=render_compacted_payload(payload))]

    def compact_if_needed(self, messages: list[AgentChatMessage]) -> list[AgentChatMessage]:
        if estimate_memory_message_tokens(messages) < self._compression_threshold_tokens:
            return messages
        return self.compact_messages(messages)
