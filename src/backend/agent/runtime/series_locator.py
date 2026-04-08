from __future__ import annotations

import json

from pydantic import BaseModel, Field

from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class SeriesLocateDecision(BaseModel):
    video_ids: list[str] = Field(default_factory=list)
    reason: str = ""


SERIES_LOCATOR_SYSTEM_PROMPT = (
    "你是视频知识工作台中的系列定位候选选择器。\n"
    "你的任务不是回答用户，而是基于整个系列各视频的 summary，选出最值得继续读取 transcript 的候选视频。\n"
    "规则：\n"
    "1. 只能依据输入的 summary 事实做选择，不要补写未知内容。\n"
    "2. 最多返回 2 个 video_id，按相关性从高到低排序。\n"
    "3. 如果没有足够证据支持任何候选，就返回空列表。\n"
    "4. 优先选择真正提到用户概念、问题或对象的视频，不要只因为标题相似就硬选。\n"
    "5. 只输出 JSON，不要输出代码块，不要额外解释。\n"
    '6. JSON 格式固定为 {"video_ids":["..."],"reason":"..."}。'
)


def select_series_locate_candidates(
    *,
    gateway: ChatGateway,
    user_message: str,
    summary_results: list[ToolExecutionResult],
) -> SeriesLocateDecision:
    messages = [
        AgentChatMessage(role="system", content=SERIES_LOCATOR_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "user_message": user_message,
                    "videos": [_build_summary_view(item) for item in summary_results],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    raw_output = gateway.create_text_completion(messages).strip()
    return parse_json_completion(raw_output, SeriesLocateDecision)


def _build_summary_view(summary_result: ToolExecutionResult) -> dict[str, object]:
    if summary_result.tool_name != ToolName.GET_VIDEO_SUMMARY:
        raise RuntimeError("系列定位候选选择器只能基于 get_video_summary 结果运行。")
    payload = summary_result.payload
    return {
        "video_id": payload.get("video_id"),
        "title": payload.get("title"),
        "generated": payload.get("generated"),
        "one_sentence_summary": payload.get("one_sentence_summary"),
        "core_problem": payload.get("core_problem"),
        "key_takeaways": payload.get("key_takeaways", []),
        "chapters": payload.get("chapters", []),
    }
