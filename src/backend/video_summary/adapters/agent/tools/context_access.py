from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import ToolContextTag, ToolDefinition, ToolName

from backend.video_summary.adapters.agent.tools.catalog import (
    ALL_TOOL_DEFINITIONS,
    MODEL_VISIBLE_TOOL_PLANES,
    get_tool_definition,
)


def list_tool_definitions_for_context(context: AgentContext) -> list[ToolDefinition]:
    allowed_contexts = _resolve_tool_context_tags(context)
    return [tool for tool in ALL_TOOL_DEFINITIONS if any(tag in allowed_contexts for tag in tool.contexts)]


def list_model_visible_tool_definitions_for_context(context: AgentContext) -> list[ToolDefinition]:
    return [tool for tool in list_tool_definitions_for_context(context) if tool.plane in MODEL_VISIBLE_TOOL_PLANES]


def render_model_visible_actions_for_context(context: AgentContext) -> str:
    action_tools = [
        tool
        for tool in list_model_visible_tool_definitions_for_context(context)
        if tool.plane.value == "ui_action"
    ]
    if not action_tools:
        return "(none)"
    return "\n".join(
        f"- {tool.name.value}: {tool.title}。{tool.description}"
        for tool in action_tools
    )


def render_model_visible_actions_for_scope(
    *,
    scope_type: str,
    series_id: str,
    video_id: str = "",
) -> str:
    return render_model_visible_actions_for_context(
        AgentContext(
            session_id=f"{scope_type}|{series_id or 'unknown'}|classifier",
            scope_type=scope_type,
            series_id=series_id or None,
            video_id=video_id or None,
        )
    )


def tool_is_available_in_context(tool_name: ToolName, context: AgentContext) -> bool:
    tool = get_tool_definition(tool_name)
    allowed_contexts = _resolve_tool_context_tags(context)
    return any(tag in allowed_contexts for tag in tool.contexts)


def _resolve_tool_context_tags(context: AgentContext) -> tuple[ToolContextTag, ...]:
    if context.scope_type == "video":
        return (ToolContextTag.VIDEO,)
    return (ToolContextTag.SERIES,)
