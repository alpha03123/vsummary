"""Agent 多轮对话消息的「渲染 + 压缩」工具。

提供三件事：把消息历史序列化成可读文本、按启发式估算 token 数、
在超过阈值时调用 LLM 把旧消息压成一条系统消息。本模块不做磁盘
持久化——消息的存档由 `AgentSessionStore` 负责。
"""

from __future__ import annotations

from math import ceil

from backend.agent.context.semantic_compactor import compact_conversation_messages, render_compacted_payload
from backend.agent.ports import ChatGateway
from backend.agent.schemas.messages import AgentChatMessage


def render_memory_messages(messages: list[AgentChatMessage]) -> str:
    """把消息历史序列化为 `role: content` 的可读文本。

    仅保留内容为字符串且非空白的消息；非字符串内容（如工具调用结构）
    在此处被忽略，避免把多模态载荷直接拼进文本。

    Args:
        messages: 任意来源的消息列表（通常是会话历史）。

    Returns:
        多行字符串，每行一条消息；末尾空白已被裁剪。
    """

    lines = [
        f"{message.role}: {message.content.strip()}"
        for message in messages
        if isinstance(message.content, str) and message.content.strip()
    ]
    return "\n".join(lines).strip()


def estimate_memory_message_tokens(messages: list[AgentChatMessage]) -> int:
    """用 UTF-8 字节数 / 3 的启发式估算消息历史的 token 数。

    这是一个粗略的上界（中文 UTF-8 偏长时略高估，英文略低估），
    目的是在不依赖分词器的前提下给出「是否需要压缩」的可比较数值。

    Args:
        messages: 待估算的消息列表。

    Returns:
        估算的 token 数；空消息列表返回 0，否则至少为 1。
    """

    text = render_memory_messages(messages)
    if not text:
        return 0
    return max(1, ceil(len(text.encode("utf-8")) / 3))


class MemoryMessageCompactor:
    """消息历史的「按需压缩」封装。

    把会话历史压成单条 system 消息，以腾出上下文窗口给后续轮次。
    压缩仅在估算 token 达到 `context_window_tokens * compression_ratio`
    阈值时触发；阈值以下的消息原样返回，避免无谓的 LLM 调用开销。

    Attributes:
        compression_threshold_tokens: 当前触发压缩的 token 阈值
            （只读），由构造期 `context_window_tokens * compression_ratio`
            一次性算出。
    """

    def __init__(
        self,
        *,
        gateway: ChatGateway,
        context_window_tokens: int,
        compression_ratio: float = 0.90,
    ) -> None:
        """初始化压缩器。

        Args:
            gateway: 用于调用 LLM 完成压缩的 `ChatGateway`。
            context_window_tokens: 模型上下文窗口大小（token），
                压缩阈值基于它计算。
            compression_ratio: 压缩触发比例，默认 0.90 即「占满
                90% 才压缩」，给系统提示词/本轮消息预留一定余量。
        """

        self._gateway = gateway
        self._context_window_tokens = context_window_tokens
        self._compression_ratio = compression_ratio
        self._compression_threshold_tokens = int(context_window_tokens * compression_ratio)

    @property
    def compression_threshold_tokens(self) -> int:
        """当前触发压缩的 token 阈值。"""

        return self._compression_threshold_tokens

    def compact_messages(self, messages: list[AgentChatMessage]) -> list[AgentChatMessage]:
        """无条件把消息列表压缩为单条 system 消息。

        实际压缩动作委派给 `context.semantic_compactor`，
        本方法只负责「把压缩结果封装成单条 system 消息」。

        Args:
            messages: 待压缩的原始消息列表。

        Returns:
            仅含一条 system 消息的列表，内容为压缩后的语义摘要。
        """

        payload = compact_conversation_messages(
            gateway=self._gateway,
            messages=messages,
        )
        return [AgentChatMessage(role="system", content=render_compacted_payload(payload))]

    def compact_if_needed(self, messages: list[AgentChatMessage]) -> list[AgentChatMessage]:
        """在 token 估算达到阈值时压缩，否则原样返回。

        Args:
            messages: 当前轮次的消息历史。

        Returns:
            压缩后的列表，或与输入完全相同的引用（未触发压缩时）。
        """

        if estimate_memory_message_tokens(messages) < self._compression_threshold_tokens:
            return messages
        return self.compact_messages(messages)
