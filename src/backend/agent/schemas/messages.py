"""Agent 视角的对话消息模型。

业务意图：Agent 内部流转的"消息"既需要兼容 LiteLLM/OpenAI 角色集合，
又需要额外携带本系统的"引用"（citations），便于在 LLM 之外的中间节点
（压缩、渲染）里复用同一份结构。
"""

from __future__ import annotations

from backend.core.chat import ChatMessage, MessageRole


AgentChatMessage = ChatMessage
