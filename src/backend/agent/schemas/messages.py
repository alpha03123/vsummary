"""Agent 视角的对话消息模型。

业务意图：Agent 内部流转的"消息"既需要兼容 LiteLLM/OpenAI 角色集合，
又需要额外携带本系统的"引用"（citations），便于在 LLM 之外的中间节点
（压缩、渲染）里复用同一份结构。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.agent.schemas.action_plan import CitationReference


MessageRole = Literal["system", "user", "assistant"]


class AgentChatMessage(BaseModel):
    """一条 Agent 视角的对话消息。

    Attributes:
        role: 消息角色，仅允许 `system` / `user` / `assistant`，与 LiteLLM
            的 `messages` 数组保持一致。
        content: 消息文本主体。
        citations: 仅在 `role == "assistant"` 时使用的引用列表；其他角色下
            通常为空。带 `citations` 的助手消息可在前端被还原成"带引用的答案"。
    """

    role: MessageRole
    content: str
    citations: list[CitationReference] = Field(default_factory=list)
