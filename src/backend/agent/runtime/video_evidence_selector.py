from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.messages import AgentChatMessage


class VideoEvidenceMode(str, Enum):
    SUMMARY = "summary"
    TRANSCRIPT = "transcript"
    FALLBACK = "fallback"


class VideoEvidenceDecision(BaseModel):
    mode: VideoEvidenceMode
    reason: str = ""


VIDEO_EVIDENCE_SELECTOR_SYSTEM_PROMPT = (
    "你是视频知识工作台中的证据选择器。\n"
    "你的任务不是回答用户，而是判断：当前视频问题在首轮更适合先读取 summary、先读取 transcript，还是交给上层 runtime 做保守兜底。\n"
    "规则：\n"
    "1. 概括、总结、主题、学习路径、讲了什么，这类优先 summary。\n"
    "2. 原话、逐字稿、字幕、具体说法、原文依据、精确表述，这类优先 transcript。\n"
    "3. 如果问题明显不是视频内容问答，例如打开工具、生成内容、视频定位、超范围请求，则返回 fallback。\n"
    "4. 只输出 JSON，不要输出代码块，不要额外解释。\n"
    '5. JSON 格式固定为 {"mode":"summary|transcript|fallback","reason":"..."}。'
)


def classify_video_evidence_need(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
) -> VideoEvidenceDecision:
    messages = [
        AgentChatMessage(role="system", content=VIDEO_EVIDENCE_SELECTOR_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "user_message": user_message,
                    "context": _build_classifier_context(context),
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    raw_output = gateway.create_text_completion(messages).strip()
    return parse_json_completion(raw_output, VideoEvidenceDecision)


def _build_classifier_context(context: AgentContext) -> dict[str, object]:
    return {
        "scope_type": context.scope_type,
        "series_id": context.series_id,
        "video_id": context.video_id,
        "selected_tool": context.selected_tool,
        "recent_messages": context.recent_messages,
    }
