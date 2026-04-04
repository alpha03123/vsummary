from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import OpenSeriesHomeCall, ToolDefinition, ToolExecutionResult, ToolName

OPEN_SERIES_HOME_TOOL = ToolDefinition(
    name=ToolName.OPEN_SERIES_HOME,
    title="打开系列首页",
    description="切换到当前 series 的主页工具页。",
)


def execute_open_series_home(call: OpenSeriesHomeCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_SERIES_HOME,
        status="ok",
        payload={"selected_tool": "series-home"},
    )
