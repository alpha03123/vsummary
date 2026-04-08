from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel

from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class NoteSource(str, Enum):
    SUMMARY = "summary"
    TRANSCRIPT = "transcript"


class VideoNoteDraft(BaseModel):
    note_title: str
    note_content: str
    reason: str = ""


VIDEO_NOTE_DRAFTER_SYSTEM_PROMPT = (
    "你是视频知识工作台中的笔记整理器。\n"
    "你的任务是基于当前视频的已读证据，生成一条适合直接保存到笔记区的标题和正文。\n"
    "规则：\n"
    "1. 只能依据输入证据整理，不要补写未出现的事实。\n"
    "2. 标题要简洁明确，像用户之后愿意再次打开查看的一条学习笔记。\n"
    "3. 正文优先整理重点、主线、关键结论；如果证据不足，要诚实保守。\n"
    "4. 输出必须适合直接保存，不要写成对话口吻，不要写“我帮你整理了”。\n"
    "5. 只输出 JSON，不要输出代码块，不要额外解释。\n"
    '6. JSON 格式固定为 {"note_title":"...","note_content":"...","reason":"..."}。'
)


def draft_video_note(
    *,
    gateway: ChatGateway,
    user_message: str,
    evidence_result: ToolExecutionResult,
) -> VideoNoteDraft:
    messages = [
        AgentChatMessage(role="system", content=VIDEO_NOTE_DRAFTER_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "user_message": user_message,
                    "source_type": _resolve_note_source(evidence_result).value,
                    "evidence": evidence_result.payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    raw_output = gateway.create_text_completion(messages).strip()
    return parse_json_completion(raw_output, VideoNoteDraft)


def _resolve_note_source(evidence_result: ToolExecutionResult) -> NoteSource:
    if evidence_result.tool_name == ToolName.GET_VIDEO_SUMMARY:
        return NoteSource.SUMMARY
    if evidence_result.tool_name == ToolName.GET_VIDEO_TRANSCRIPT:
        return NoteSource.TRANSCRIPT
    raise RuntimeError("笔记整理器只能基于 summary 或 transcript 结果运行。")
