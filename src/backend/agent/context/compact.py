from __future__ import annotations

from math import ceil

from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import ChatGateway
from backend.agent.context.semantic_compactor import compact_conversation_messages, render_compacted_payload
from backend.agent.schemas.messages import AgentChatMessage

DEFAULT_CONTEXT_WINDOW_TOKENS = 1_000_000
DEFAULT_COMPACT_THRESHOLD_RATIO = 0.80
DEFAULT_KEEP_TAIL_MESSAGES = 6


class AgentMemoryCompactionService:
    def __init__(
        self,
        *,
        gateway: ChatGateway,
        memory_store: AgentMemoryStore,
        context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
        compact_threshold_ratio: float = DEFAULT_COMPACT_THRESHOLD_RATIO,
        keep_tail_messages: int = DEFAULT_KEEP_TAIL_MESSAGES,
    ) -> None:
        self._gateway = gateway
        self._memory_store = memory_store
        self._context_window_tokens = context_window_tokens
        self._compact_threshold_ratio = compact_threshold_ratio
        self._compact_threshold_tokens = int(context_window_tokens * compact_threshold_ratio)
        self._keep_tail_messages = keep_tail_messages

    def compact_if_needed(self, session_id: str) -> bool:
        messages = self._memory_store.get_messages(session_id)
        if len(messages) <= self._keep_tail_messages:
            return False
        if _estimate_messages_tokens(messages) < self._compact_threshold_tokens:
            return False

        head_messages = messages[:-self._keep_tail_messages]
        tail_messages = messages[-self._keep_tail_messages:]
        compacted_payload = compact_conversation_messages(
            gateway=self._gateway,
            messages=head_messages,
        )
        summary_message = AgentChatMessage(
            role="system",
            content=render_compacted_payload(compacted_payload),
        )
        self._memory_store.replace_messages(session_id, [summary_message, *tail_messages])
        return True


def _estimate_messages_tokens(messages: list[AgentChatMessage]) -> int:
    text = "\n".join(f"{message.role}:{message.content}" for message in messages).strip()
    if not text:
        return 0
    return max(1, ceil(len(text.encode("utf-8")) / 3))
