from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    OpenVideoCall,
    ToolDefinition,
    ToolExecutionResult,
    ToolName,
    VideoSeekCall,
)

OPEN_VIDEO_TOOL = ToolDefinition(
    name=ToolName.OPEN_VIDEO,
    title="打开视频工具",
    description="切换到视频预览工具页。",
)

VIDEO_SEEK_TOOL = ToolDefinition(
    name=ToolName.VIDEO_SEEK,
    title="跳转视频时间点",
    description="打开视频工具，并跳到指定秒数。",
    arguments={"seek_seconds": "需要跳转到的视频秒数"},
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
            "selected_tool": "video",
            "seek_seconds": call.seek_seconds,
        },
    )
