from __future__ import annotations

import json

from pydantic import BaseModel, Field

from backend.agent.ports import ChatGateway
from backend.agent.prompts import COMPACTOR_SYSTEM_PROMPT
from backend.agent.schemas.messages import AgentChatMessage


class CompactedConversationPayload(BaseModel):
    summary: str
    confirmed_facts: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


def compact_conversation_messages(
    *,
    gateway: ChatGateway,
    messages: list[AgentChatMessage],
) -> CompactedConversationPayload:
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
