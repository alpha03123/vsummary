from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    OpenSeriesHomeCall,
    OpenSeriesOverviewCall,
    ToolDefinition,
    ToolContextTag,
    ToolExecutionResult,
    ToolName,
    ToolPlane,
)

OPEN_SERIES_HOME_TOOL = ToolDefinition(
    name=ToolName.OPEN_SERIES_HOME,
    title="打开系列首页",
    description="切换到当前 series 的主页工具页。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.SERIES,),
)

OPEN_SERIES_OVERVIEW_TOOL = ToolDefinition(
    name=ToolName.OPEN_SERIES_OVERVIEW,
    title="打开系列概览",
    description="切换到当前 series 的概览页，用于查看整个系列的视频分布与覆盖范围。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.SERIES,),
)


def execute_open_series_home(call: OpenSeriesHomeCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_SERIES_HOME,
        status="ok",
        payload={"selected_tool": "series-home"},
    )


def execute_open_series_overview(call: OpenSeriesOverviewCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_SERIES_OVERVIEW,
        status="ok",
        payload={"selected_tool": "series-overview"},
    )
