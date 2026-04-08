from __future__ import annotations

import json

from pydantic import BaseModel

from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class VideoSeekDecision(BaseModel):
    seek_seconds: float
    match_end_seconds: float | None = None
    matched_text: str = ""
    chapter_title: str = ""
    reason: str = ""


VIDEO_SEEK_LOCATOR_SYSTEM_PROMPT = (
    "你是视频知识工作台中的定位器。\n"
    "你的任务是根据用户问题和视频转写，输出最相关的时间点用于视频跳转。\n"
    "规则：\n"
    "1. 必须从给定 transcript 片段中找出最相关的位置。\n"
    "2. 返回的 seek_seconds 应该是用户最适合开始观看的位置。\n"
    "3. 如果匹配内容跨多句，可以同时给出 match_end_seconds。\n"
    "4. 只输出 JSON，不要输出代码块，不要额外解释。\n"
    '5. JSON 格式固定为 {"seek_seconds":number,"match_end_seconds":number|null,"matched_text":"...","chapter_title":"...","reason":"..."}。'
)


def locate_video_seek(
    *,
    gateway: ChatGateway,
    user_message: str,
    transcript_result: ToolExecutionResult,
) -> VideoSeekDecision:
    messages = [
        AgentChatMessage(role="system", content=VIDEO_SEEK_LOCATOR_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "user_message": user_message,
                    "transcript": _build_transcript_view(transcript_result),
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    raw_output = gateway.create_text_completion(messages).strip()
    return parse_json_completion(raw_output, VideoSeekDecision)


def _build_transcript_view(transcript_result: ToolExecutionResult) -> dict[str, object]:
    if transcript_result.tool_name != ToolName.GET_VIDEO_TRANSCRIPT:
        raise RuntimeError("定位器只能基于 get_video_transcript 结果运行。")
    payload = transcript_result.payload
    return {
        "video_id": payload.get("video_id"),
        "title": payload.get("title"),
        "duration_seconds": payload.get("duration_seconds"),
        "segments": payload.get("segments", []),
    }
