from __future__ import annotations

from math import ceil

from backend.agent.memory.store import AgentMemoryStore
from backend.agent.schemas.messages import AgentChatMessage

DEFAULT_COMPACT_THRESHOLD_TOKENS = 12_000
DEFAULT_KEEP_TAIL_MESSAGES = 6


class AgentMemoryCompactionService:
    def __init__(
        self,
        *,
        memory_store: AgentMemoryStore,
        compact_threshold_tokens: int = DEFAULT_COMPACT_THRESHOLD_TOKENS,
        keep_tail_messages: int = DEFAULT_KEEP_TAIL_MESSAGES,
    ) -> None:
        self._memory_store = memory_store
        self._compact_threshold_tokens = compact_threshold_tokens
        self._keep_tail_messages = keep_tail_messages

    def compact_if_needed(self, session_id: str) -> bool:
        messages = self._memory_store.get_messages(session_id)
        if len(messages) <= self._keep_tail_messages:
            return False
        if _estimate_messages_tokens(messages) < self._compact_threshold_tokens:
            return False

        head_messages = messages[:-self._keep_tail_messages]
        tail_messages = messages[-self._keep_tail_messages:]
        summary_message = AgentChatMessage(
            role="system",
            content=_build_summary_message(head_messages),
        )
        self._memory_store.replace_messages(session_id, [summary_message, *tail_messages])
        return True


def _build_summary_message(messages: list[AgentChatMessage]) -> str:
    lines = ["以下是更早对话的压缩摘要，请在后续规划中把它当作已知上下文："]
    for index, message in enumerate(messages, start=1):
        speaker = "用户" if message.role == "user" else "助手" if message.role == "assistant" else "系统"
        normalized = " ".join(message.content.split())
        if len(normalized) > 160:
            normalized = f"{normalized[:157]}..."
        lines.append(f"{index}. {speaker}：{normalized}")
    return "\n".join(lines)


def _estimate_messages_tokens(messages: list[AgentChatMessage]) -> int:
    text = "\n".join(f"{message.role}:{message.content}" for message in messages).strip()
    if not text:
        return 0
    return max(1, ceil(len(text.encode("utf-8")) / 3))
