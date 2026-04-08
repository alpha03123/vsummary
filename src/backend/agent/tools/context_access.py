from __future__ import annotations

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.schemas.tool_calls import ToolContextTag, ToolDefinition, ToolName

from backend.agent.tools.catalog import (
    ALL_TOOL_DEFINITIONS,
    MODEL_VISIBLE_TOOL_PLANES,
    get_tool_definition,
)


def list_tool_definitions_for_context(context: AgentContext) -> list[ToolDefinition]:
    allowed_contexts = _resolve_tool_context_tags(context)
    return [tool for tool in ALL_TOOL_DEFINITIONS if any(tag in allowed_contexts for tag in tool.contexts)]


def list_model_visible_tool_definitions_for_context(context: AgentContext) -> list[ToolDefinition]:
    return [tool for tool in list_tool_definitions_for_context(context) if tool.plane in MODEL_VISIBLE_TOOL_PLANES]


def tool_is_available_in_context(tool_name: ToolName, context: AgentContext) -> bool:
    tool = get_tool_definition(tool_name)
    allowed_contexts = _resolve_tool_context_tags(context)
    return any(tag in allowed_contexts for tag in tool.contexts)


def _resolve_tool_context_tags(context: AgentContext) -> tuple[ToolContextTag, ...]:
    if context.scope_type == "video":
        return (ToolContextTag.VIDEO,)
    if context.inspection_stage == InspectionStage.SERIES_DISCOVERY:
        return (ToolContextTag.SERIES_DISCOVERY,)
    return (
        ToolContextTag.SERIES_DISCOVERY,
        ToolContextTag.SERIES_INSPECTION,
    )
