from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.messages import AgentChatMessage


class SeriesEvidenceMode(str, Enum):
    SUMMARY = "summary"
    FALLBACK = "fallback"


class SeriesEvidenceDecision(BaseModel):
    mode: SeriesEvidenceMode
    reason: str = ""


SERIES_EVIDENCE_SELECTOR_SYSTEM_PROMPT = (
    "你是视频知识工作台中的系列证据选择器。\n"
    "你的任务不是回答用户，而是判断：当前 series 问题是否应该走“先列系列视频，再批量读取 summary”的系列证据工作流。\n"
    "规则：\n"
    "1. 主题、主线、学习路径、系列讲了什么、系列差异、系列对比，这类返回 summary。\n"
    "2. 如果请求明显是打开页面、生成内容、超范围问题，返回 fallback。\n"
    "3. 只输出 JSON，不要输出代码块，不要额外解释。\n"
    '4. JSON 格式固定为 {"mode":"summary|fallback","reason":"..."}。'
)


def classify_series_evidence_need(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
) -> SeriesEvidenceDecision:
    messages = [
        AgentChatMessage(role="system", content=SERIES_EVIDENCE_SELECTOR_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "user_message": user_message,
                    "context": {
                        "scope_type": context.scope_type,
                        "series_id": context.series_id,
                        "selected_tool": context.selected_tool,
                        "recent_messages": context.recent_messages,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    raw_output = gateway.create_text_completion(messages).strip()
    return parse_json_completion(raw_output, SeriesEvidenceDecision)
