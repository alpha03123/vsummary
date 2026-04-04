from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import GenerateMindmapCall, ToolDefinition, ToolExecutionResult, ToolName

MINDMAP_TOOL = ToolDefinition(
    name=ToolName.GENERATE_MINDMAP,
    title="生成导图",
    description="切换到思维导图工具，并在需要时触发生成。",
)


def execute_generate_mindmap(call: GenerateMindmapCall, context: AgentContext) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=ToolName.GENERATE_MINDMAP,
        status="ok",
        payload={"selected_tool": "mindmap", "action": "generate_mindmap"},
    )
