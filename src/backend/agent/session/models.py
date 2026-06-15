"""Agent 会话持久化的数据模型。

定义「会话快照」与「消息条目」两种 Pydantic 模型——这是
`AgentSessionStore` 写入磁盘 / 从磁盘读回的统一形态。
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.action_plan import CitationReference


class AgentSessionMessageEntry(BaseModel):
    """会话历史中的单条消息。

    相比 `AgentChatMessage`（运行期 DTO），这里把时间戳和引用都
    固化为字段，方便落盘后无需依赖运行时上下文即可重建。

    Attributes:
        role: 消息角色（"user" / "assistant" / "system" 等）。
        content: 消息文本内容。
        created_at: 该条目创建时间的 ISO-8601 字符串（UTC）。
        citations: 助手回复带上的引用列表，默认为空。
    """

    role: str
    content: str
    created_at: str
    citations: list[CitationReference] = Field(default_factory=list)


class AgentSessionSnapshot(BaseModel):
    """一个会话的完整可恢复快照。

    包含会话元信息（`session_id` / `memory_key`）、最近一次绑定的
    `AgentContext` 与消息历史；由 `AgentSessionStore` 整体读写，
    不支持部分更新。`memory_key` 用于在同一会话内切换工作区时
    让 LLM 记忆按工作区隔离。

    Attributes:
        session_id: 会话唯一 ID。
        memory_key: 当前消息历史所绑定的「工作区记忆桶」键；
            不同工作区（如不同 series）的压缩记忆互不共享。
        context: 该会话最近一次使用的 `AgentContext` 副本。
        messages: 消息历史（按时间顺序）。
        updated_at: 快照最近一次写入时间的 ISO-8601 字符串。

    Properties:
        message_count: 消息历史的长度，便于上层做轻量判断。
    """

    session_id: str
    memory_key: str
    context: AgentContext
    messages: list[AgentSessionMessageEntry] = Field(default_factory=list)
    updated_at: str

    @property
    def message_count(self) -> int:
        """返回消息历史中的条目数。"""

        return len(self.messages)


def utc_now_iso() -> str:
    """返回当前 UTC 时间的 ISO-8601 字符串。"""

    return datetime.now(timezone.utc).isoformat()
