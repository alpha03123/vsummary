"""Agent 图的会话记录模块，负责将每个回合持久化到会话存储。

本模块定义 `AgentGraphSessionRecorder`——在每个回合结束时将用户消息、助手
回复与引用写入 `AgentSessionStore`，并可选地对历史消息做压缩。
"""

from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.memory.messages import MemoryMessageCompactor
from backend.agent.ports import AgentSessionStore
from backend.agent.schemas.action_plan import AgentTurnResult, CitationReference
from backend.agent.schemas.messages import AgentChatMessage


class AgentGraphSessionRecorder:
    """Agent 图会话记录器，负责在每个回合结束时持久化对话历史。

    业务意图：将图运行产出的助手消息与引用连同用户消息一起追加到会话存储中，
    使下一回合能从完整的多轮上下文中加载 `memory_messages`。

    关键不变式：
    - 追加消息时总是先加载已有快照，再追加本轮用户+助手对，保证消息顺序；
    - 若 `memory_compactor` 已注入，追加后立即对消息列表做压缩；
    - `session_store` 为 `None` 时所有操作均为空操作（优雅降级）。
    """
    def __init__(
        self,
        *,
        session_store: AgentSessionStore | None = None,
        memory_compactor: MemoryMessageCompactor | None = None,
    ) -> None:
        """注入会话存储端口与可选的消息压缩器。

        Args:
            session_store: 会话持久化端口；为 `None` 时不记录多轮历史。
            memory_compactor: 可选的消息压缩器，在追加消息后对全量历史做压缩；
                为 `None` 时跳过压缩。
        """
        self._session_store = session_store
        self._memory_compactor = memory_compactor

    @property
    def session_store(self) -> AgentSessionStore | None:
        """已注入的会话存储端口；可能为 `None`."""
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
        """持久化当前回合的对话到会话存储。

        先加载已有快照消息，再追加本轮的用户消息与助手回复（含引用），最后
        可选地对全量消息做压缩。`session_store` 为 `None` 时直接跳过。

        Args:
            session_id: 会话唯一 ID。
            context: 当前会话的 `AgentContext`（scope、目标资源等）。
            user_message: 用户最新问题原文。
            result: 图运行结束后的完整状态字典（当前保留未用，供未来扩展）。
            turn_result: 构建好的 `AgentTurnResult`，含助手消息与引用。
        """
        if self._session_store is None:
            return
        messages = self._build_next_memory_messages(
            session_id=session_id,
            user_message=user_message,
            assistant_message=turn_result.assistant_message,
            assistant_citations=turn_result.citations,
        )
        self._session_store.append_turn(
            session_id=session_id,
            memory_key=session_id,
            context=context,
            messages=messages,
        )

    def clear_session(self, session_id: str) -> None:
        """清除指定会话的全部快照记录。

        Args:
            session_id: 目标会话 ID。
        """
        if self._session_store is not None:
            self._session_store.clear_snapshot(session_id)

    def _build_next_memory_messages(
        self,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
        assistant_citations: list[CitationReference],
    ) -> list[AgentChatMessage]:
        """构建下回合使用的 memory 消息列表（快照消息 + 本轮用户/助手对）。

        先读取已有快照中的历史消息，再追加本轮用户消息与助手回复，最后可选
        地对全量列表做压缩（当消息数超阈值时由 compactor 裁剪或总结旧消息）。

        Args:
            session_id: 会话唯一 ID，用于读取已有快照。
            user_message: 本轮用户问题原文。
            assistant_message: 本轮助手回复全文。
            assistant_citations: 本轮助手引用的证据列表。

        Returns:
            已追加并可选压缩后的 `AgentChatMessage` 列表。
        """
        messages: list[AgentChatMessage] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                messages.extend(
                    AgentChatMessage(role=item.role, content=item.content, citations=item.citations)
                    for item in snapshot.messages
                )
        messages.extend(
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=assistant_message, citations=assistant_citations),
            ]
        )
        if self._memory_compactor is not None:
            return self._memory_compactor.compact_if_needed(messages)
        return messages
