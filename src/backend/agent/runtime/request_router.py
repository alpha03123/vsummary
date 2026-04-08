from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.messages import AgentChatMessage


class RouteKind(str, Enum):
    SERIES_SUMMARY = "series_summary"
    SERIES_LOCATE = "series_locate"
    VIDEO_SUMMARY = "video_summary"
    VIDEO_TRANSCRIPT = "video_transcript"
    VIDEO_SEEK = "video_seek"
    SAVE_NOTE = "save_note"
    OPEN_TOOL = "open_tool"
    GENERATE_OVERVIEW = "generate_overview"
    GENERATE_MINDMAP = "generate_mindmap"
    OUT_OF_SCOPE = "out_of_scope"
    FALLBACK = "fallback"


class RouteToolName(str, Enum):
    OPEN_SERIES_HOME = "open_series_home"
    OPEN_SERIES_OVERVIEW = "open_series_overview"
    OPEN_OVERVIEW = "open_overview"
    OPEN_MINDMAP = "open_mindmap"
    OPEN_KNOWLEDGE_CARDS = "open_knowledge_cards"
    OPEN_NOTES = "open_notes"
    OPEN_VIDEO = "open_video"


class InitialRouteDecision(BaseModel):
    kind: RouteKind
    tool_name: RouteToolName | None = None
    reason: str = ""


REQUEST_ROUTER_SYSTEM_PROMPT = (
    "你是视频知识工作台中的首轮请求路由器。\n"
    "你不负责回答用户，只负责把请求路由到最合适的首轮执行路径。\n"
    "规则：\n"
    "1. series 的概括、主题、学习路径、系列讲了什么，返回 series_summary。\n"
    "2. series 范围内找某个概念/对象在哪个视频提过、系列里哪里讲过，返回 series_locate。\n"
    "3. video 的概括、总结、主要讲了什么，返回 video_summary。\n"
    "4. video 的原话、逐字稿、字幕、具体说法，返回 video_transcript。\n"
    "5. video 的定位类问题，例如“在哪个位置提到”“什么时间提到”“视频哪里提到”，返回 video_seek。\n"
    "6. 请求整理重点、记录笔记、帮我记一下时，返回 save_note。\n"
    "7. 明确的打开/切换类请求，返回 open_tool，并填写 tool_name。\n"
    "8. 明确的生成概况，返回 generate_overview。\n"
    "9. 明确的生成导图，返回 generate_mindmap。\n"
    "10. 明显超出视频知识工作台范围的问题，例如旅游攻略、写通用文案、闲聊外部话题，返回 out_of_scope。\n"
    "11. 其他仍属于工作台范围、但一时难以细分的请求，优先归到最接近的内容路径：series 走 series_summary，video 走 video_summary 或 video_transcript。\n"
    "12. 只输出 JSON，不要输出代码块，不要额外解释。\n"
    '13. JSON 格式固定为 {"kind":"...","tool_name":"...或null","reason":"..."}。\n'
    "14. 如果 kind=open_tool，tool_name 只能填写以下精确值之一："
    "open_series_home, open_series_overview, open_overview, open_mindmap, open_knowledge_cards, open_notes, open_video。\n"
    "15. 不要填写简写，例如 overview、series-overview、notes、mindmap 这类都不允许。"
    "\n"
    "16. 常见示例：\n"
    "- “这个系列主要讲了哪些主题” -> kind=series_summary\n"
    "- “这个系列里哪里讲过 Nacos 3” -> kind=series_locate\n"
    "- “这个视频主要讲了什么” -> kind=video_summary\n"
    "- “视频原话里是怎么说的” -> kind=video_transcript\n"
    "- “百度地图 API Key 在视频什么位置提到的” -> kind=video_seek\n"
    "- “帮我记一下这个视频的重点” -> kind=save_note\n"
    "- “打开系列概览” -> kind=open_tool, tool_name=open_series_overview\n"
    "- “打开概况” -> kind=open_tool, tool_name=open_overview\n"
    "- “打开思维导图” -> kind=open_tool, tool_name=open_mindmap\n"
    "- “打开知识卡片” -> kind=open_tool, tool_name=open_knowledge_cards\n"
    "- “打开笔记” -> kind=open_tool, tool_name=open_notes\n"
    "- “打开视频” -> kind=open_tool, tool_name=open_video\n"
    "- “生成概况” -> kind=generate_overview\n"
    "- “生成导图” -> kind=generate_mindmap\n"
    "- “帮我写一份旅游攻略” -> kind=out_of_scope\n"
)


def classify_initial_route(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
) -> InitialRouteDecision:
    messages = [
        AgentChatMessage(role="system", content=REQUEST_ROUTER_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "user_message": user_message,
                    "context": {
                        "scope_type": context.scope_type,
                        "series_id": context.series_id,
                        "video_id": context.video_id,
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
    return parse_json_completion(raw_output, InitialRouteDecision)
