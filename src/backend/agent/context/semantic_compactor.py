"""把"较旧的对话消息"压缩成可继续使用的语义摘要。

业务意图：当会话历史膨胀到逼近上下文窗口时，调用 `compact_conversation_messages`
让 LLM 把历史消息压成"摘要 + 已确认事实 + 待继续事项 + 重要约束"四类要点，
再由 `render_compacted_payload` 渲染为可注入到系统提示词的纯文本，作为后续
轮次的"已知上下文"使用。

压缩策略：
- 保留：用户目标、已确认事实、未完成事项、重要约束等"会影响后续回答"的内容。
- 丢弃：寒暄、重复表述、铺垫性话语（具体规则由 `COMPACTOR_SYSTEM_PROMPT` 约束）。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from backend.agent.ports import ChatGateway
from backend.agent.prompts import COMPACTOR_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage


class CompactedConversationPayload(BaseModel):
    """LLLM 压缩后产出的"语义摘要"结构化结果。

    四个字段共同构成"可继续使用"的历史信息载体：
    - `summary`：一段连续叙述，概括整段历史。
    - `confirmed_facts`：在历史中已被双方共同认定的事实列表。
    - `open_threads`：仍未完成、需要在后续轮次继续推进的事项。
    - `constraints`：影响后续回答的限制条件（用户偏好、硬性要求等）。
    """

    summary: str
    confirmed_facts: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


def compact_conversation_messages(
    *,
    gateway: ChatGateway,
    messages: list[AgentChatMessage],
) -> CompactedConversationPayload:
    """调用 LLM 把 `messages` 压缩为 `CompactedConversationPayload`。

    算法：
    1. 把 `messages` 序列化为 `{role, content}` 字典列表；
    2. 构造"系统提示词（`COMPACTOR_SYSTEM_PROMPT`）+ 用户消息（JSON 化的历史）"
       的两段式提示词；
    3. 用 `ChatGateway` 的结构化补全接口强制 LLM 按 Pydantic schema 输出，
       得到可直接使用的 `CompactedConversationPayload`。

    Args:
        gateway: 实际发起 LLM 调用的 `ChatGateway` Port 实现。
        messages: 待压缩的历史消息。

    Returns:
        LLM 压缩后的 `CompactedConversationPayload`。
    """
    rendered_messages = [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in messages
    ]
    prompt_messages = [
        AgentChatMessage(role="system", content=COMPACTOR_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "messages": rendered_messages,
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    return gateway.create_structured_completion(
        prompt_messages,
        response_model=CompactedConversationPayload,
    )


def render_compacted_payload(payload: CompactedConversationPayload) -> str:
    """把压缩产物渲染成可注入到系统提示词的纯文本。

    输出结构：
    - 固定首行说明："以下是更早对话的语义压缩摘要，请把它当作已知上下文："；
    - 非空的 `summary` 以"摘要：…"接续；
    - 其余三个列表各自带有"已确认事实 / 待继续事项 / 重要约束"的中文标题，
      以 `-` 列出非空项；空列表被整段省略。

    Args:
        payload: 由 `compact_conversation_messages` 产出的压缩结果。

    Returns:
        多行 Markdown 风格的纯文本，可直接作为系统/用户消息的内容片段。
    """
    lines = ["以下是更早对话的语义压缩摘要，请把它当作已知上下文："]
    if payload.summary.strip():
        lines.append(f"摘要：{payload.summary.strip()}")
    if payload.confirmed_facts:
        lines.append("已确认事实：")
        lines.extend(f"- {item}" for item in payload.confirmed_facts if item.strip())
    if payload.open_threads:
        lines.append("待继续事项：")
        lines.extend(f"- {item}" for item in payload.open_threads if item.strip())
    if payload.constraints:
        lines.append("重要约束：")
        lines.extend(f"- {item}" for item in payload.constraints if item.strip())
    return "\n".join(lines)
