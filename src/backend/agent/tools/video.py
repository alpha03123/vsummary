from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    OpenVideoCall,
    ToolDefinition,
    ToolContextTag,
    ToolExecutionResult,
    ToolIntentTag,
    ToolName,
    ToolPlane,
    VideoSeekCall,
)

OPEN_VIDEO_TOOL = ToolDefinition(
    name=ToolName.OPEN_VIDEO,
    title="打开视频工具",
    description="切换到视频预览工具页。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.VIDEO,),
    intents=(ToolIntentTag.OPEN_TOOL,),
)

VIDEO_SEEK_TOOL = ToolDefinition(
    name=ToolName.VIDEO_SEEK,
    title="跳转视频时间点",
    description="返回最适合开始观看的时间点，并附带命中片段。",
    plane=ToolPlane.UI_ACTION,
    arguments={"seek_seconds": "需要跳转到的视频秒数"},
    contexts=(ToolContextTag.VIDEO,),
    intents=(ToolIntentTag.SEEK_VIDEO,),
)


def execute_open_video(call: OpenVideoCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_VIDEO,
        status="ok",
        payload={"selected_tool": "video"},
    )


def execute_video_seek(call: VideoSeekCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.VIDEO_SEEK,
        status="ok",
        payload={
            "seek_seconds": call.seek_seconds,
            "match_end_seconds": call.match_end_seconds,
            "matched_text": call.matched_text,
            "chapter_title": call.chapter_title,
            "query": call.query,
        },
    )
