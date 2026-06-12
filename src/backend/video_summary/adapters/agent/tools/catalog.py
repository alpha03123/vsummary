from __future__ import annotations

from backend.agent.schemas.tool_calls import (
    ToolDefinition,
    ToolName,
    ToolPlane,
)
from backend.video_summary.adapters.agent.tools.library_info import (
    GET_VIDEO_SUMMARY_TOOL,
    GET_VIDEO_TRANSCRIPT_TOOL,
    GET_VIDEO_TOOLS_TOOL,
    LIST_SERIES_VIDEOS_TOOL,
)
from backend.video_summary.adapters.agent.tools.mindmap import GENERATE_MINDMAP_TOOL, OPEN_MINDMAP_TOOL
from backend.video_summary.adapters.agent.tools.notes import OPEN_KNOWLEDGE_CARDS_TOOL, OPEN_NOTES_TOOL, SAVE_NOTE_TOOL
from backend.video_summary.adapters.agent.tools.overview import GENERATE_OVERVIEW_TOOL, OPEN_OVERVIEW_TOOL
from backend.video_summary.adapters.agent.tools.series import OPEN_SERIES_HOME_TOOL, OPEN_SERIES_OVERVIEW_TOOL
from backend.video_summary.adapters.agent.tools.video import OPEN_VIDEO_TOOL, VIDEO_SEEK_TOOL


BUSINESS_READ_TOOL_DEFINITIONS: list[ToolDefinition] = [
    LIST_SERIES_VIDEOS_TOOL,
    GET_VIDEO_SUMMARY_TOOL,
    GET_VIDEO_TOOLS_TOOL,
    GET_VIDEO_TRANSCRIPT_TOOL,
]

UI_ACTION_TOOL_DEFINITIONS: list[ToolDefinition] = [
    OPEN_SERIES_HOME_TOOL,
    OPEN_SERIES_OVERVIEW_TOOL,
    OPEN_OVERVIEW_TOOL,
    OPEN_MINDMAP_TOOL,
    OPEN_KNOWLEDGE_CARDS_TOOL,
    OPEN_NOTES_TOOL,
    GENERATE_OVERVIEW_TOOL,
    GENERATE_MINDMAP_TOOL,
    OPEN_VIDEO_TOOL,
    VIDEO_SEEK_TOOL,
    SAVE_NOTE_TOOL,
]

ALL_TOOL_DEFINITIONS: list[ToolDefinition] = [
    *BUSINESS_READ_TOOL_DEFINITIONS,
    *UI_ACTION_TOOL_DEFINITIONS,
]

MODEL_VISIBLE_TOOL_PLANES: tuple[ToolPlane, ...] = (
    ToolPlane.BUSINESS_READ,
    ToolPlane.UI_ACTION,
)

TOOL_DEFINITIONS_BY_NAME: dict[ToolName, ToolDefinition] = {tool.name: tool for tool in ALL_TOOL_DEFINITIONS}


def get_tool_definition(tool_name: ToolName) -> ToolDefinition:
    return TOOL_DEFINITIONS_BY_NAME[tool_name]


def list_tool_definitions_for_plane(plane: ToolPlane) -> list[ToolDefinition]:
    return [tool for tool in ALL_TOOL_DEFINITIONS if tool.plane == plane]


def tool_is_model_visible(tool_name: ToolName) -> bool:
    return get_tool_definition(tool_name).plane in MODEL_VISIBLE_TOOL_PLANES
