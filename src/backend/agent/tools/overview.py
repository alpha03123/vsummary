from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    GenerateOverviewCall,
    OpenOverviewCall,
    ToolDefinition,
    ToolContextTag,
    ToolExecutionResult,
    ToolIntentTag,
    ToolName,
    ToolPlane,
)

OPEN_OVERVIEW_TOOL = ToolDefinition(
    name=ToolName.OPEN_OVERVIEW,
    title="打开概况工具",
    description="切换到 AI 概况工具页。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.VIDEO,),
    intents=(ToolIntentTag.OPEN_TOOL, ToolIntentTag.GENERATE_OVERVIEW),
)

GENERATE_OVERVIEW_TOOL = ToolDefinition(
    name=ToolName.GENERATE_OVERVIEW,
    title="生成概况",
    description="当概况尚未生成时，触发生成 AI 概况。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.VIDEO,),
    intents=(ToolIntentTag.GENERATE_OVERVIEW,),
)


def execute_open_overview(call: OpenOverviewCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_OVERVIEW,
        status="ok",
        payload={"selected_tool": "overview"},
    )


def execute_generate_overview(call: GenerateOverviewCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.GENERATE_OVERVIEW,
        status="ok",
        payload={"action": "generate_overview", "selected_tool": "overview"},
    )
