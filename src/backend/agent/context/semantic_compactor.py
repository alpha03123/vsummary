from __future__ import annotations

import json

from pydantic import BaseModel, Field

from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.messages import AgentChatMessage


class CompactedConversationPayload(BaseModel):
    summary: str
    confirmed_facts: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


COMPACTOR_SYSTEM_PROMPT = (
    "你是视频知识工作台中的对话压缩器。\n"
    "你的任务是把更早的对话消息压缩成可继续使用的语义摘要。\n"
    "规则：\n"
    "1. 只能依据给定消息总结，不要编造未出现的事实。\n"
    "2. 保留真正会影响后续回答的内容：用户目标、已确认事实、未完成事项、重要约束。\n"
    "3. 删除寒暄、重复表述、无关铺垫。\n"
    "4. 输出必须紧凑，但不能损坏事实含义。\n"
    "5. 只输出 JSON，不要代码块，不要额外解释。\n"
    '6. JSON 格式固定为 {"summary":"...","confirmed_facts":["..."],"open_threads":["..."],"constraints":["..."]}。'
)


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
    raw_output = gateway.create_text_completion(prompt_messages).strip()
    return parse_json_completion(raw_output, CompactedConversationPayload)


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
