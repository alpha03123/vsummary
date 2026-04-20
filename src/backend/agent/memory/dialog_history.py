from __future__ import annotations

from math import ceil

from backend.agent.context.semantic_compactor import compact_conversation_messages, render_compacted_payload
from backend.agent.ports import ChatGateway
from backend.agent.schemas.messages import AgentChatMessage


def render_dialog_history(messages: list[AgentChatMessage]) -> str:
    lines = [
        f"{message.role}: {message.content.strip()}"
        for message in messages
        if isinstance(message.content, str) and message.content.strip()
    ]
    return "\n".join(lines).strip()


def estimate_dialog_history_tokens(dialog_history: str) -> int:
    text = dialog_history.strip()
    if not text:
        return 0
    return max(1, ceil(len(text.encode("utf-8")) / 3))


class DialogHistoryCompactor:
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

    def compact_messages(self, messages: list[AgentChatMessage]) -> str:
        payload = compact_conversation_messages(
            gateway=self._gateway,
            messages=messages,
        )
        return render_compacted_payload(payload)

    def compact_if_needed(self, messages: list[AgentChatMessage]) -> str:
        dialog_history = render_dialog_history(messages)
        if estimate_dialog_history_tokens(dialog_history) < self._compression_threshold_tokens:
            return dialog_history
        return self.compact_messages(messages)
