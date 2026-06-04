from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import (
    GenerateMindmapCall,
    OpenMindmapCall,
    ToolDefinition,
    ToolContextTag,
    ToolExecutionResult,
    ToolName,
    ToolPlane,
)

OPEN_MINDMAP_TOOL = ToolDefinition(
    name=ToolName.OPEN_MINDMAP,
    title="打开思维导图",
    description="切换到思维导图工具页。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.VIDEO,),
)

GENERATE_MINDMAP_TOOL = ToolDefinition(
    name=ToolName.GENERATE_MINDMAP,
    title="生成导图",
    description="切换到思维导图工具，并在需要时触发生成。",
    plane=ToolPlane.UI_ACTION,
    contexts=(ToolContextTag.VIDEO,),
)


def execute_open_mindmap(call: OpenMindmapCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.OPEN_MINDMAP,
        status="ok",
        payload={"selected_tool": "mindmap"},
    )


def execute_generate_mindmap(call: GenerateMindmapCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.GENERATE_MINDMAP,
        status="ok",
        payload={"selected_tool": "mindmap", "action": "generate_mindmap"},
    )
