from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.schemas.tool_calls import ToolContextTag, ToolDefinition, ToolEffectTag, ToolIntentTag, ToolName, ToolPlane
from backend.agent.tools.library_info import (
    GET_VIDEO_SUMMARY_TOOL,
    GET_VIDEO_TRANSCRIPT_TOOL,
    GET_VIDEO_TOOLS_TOOL,
    LIST_SERIES_VIDEOS_TOOL,
    create_get_video_transcript_handler,
)
from backend.agent.tools.mindmap import (
    GENERATE_MINDMAP_TOOL,
    OPEN_MINDMAP_TOOL,
    execute_generate_mindmap,
    execute_open_mindmap,
)
from backend.agent.tools.notes import (
    OPEN_KNOWLEDGE_CARDS_TOOL,
    OPEN_NOTES_TOOL,
    SAVE_NOTE_TOOL,
    execute_open_knowledge_cards,
    execute_open_notes,
    execute_save_note,
)
from backend.agent.tools.overview import (
    GENERATE_OVERVIEW_TOOL,
    OPEN_OVERVIEW_TOOL,
    execute_generate_overview,
    execute_open_overview,
)
from backend.agent.tools.series import (
    OPEN_SERIES_HOME_TOOL,
    OPEN_SERIES_OVERVIEW_TOOL,
    execute_open_series_home,
    execute_open_series_overview,
)
from backend.agent.tools.series_buffer import (
    ADD_SERIES_CANDIDATES_TOOL,
    CLEAR_SERIES_CANDIDATES_TOOL,
    REMOVE_SERIES_CANDIDATES_TOOL,
    REPLACE_SERIES_CANDIDATES_TOOL,
    VIEW_SERIES_CANDIDATES_TOOL,
    create_add_series_candidates_handler,
    create_clear_series_candidates_handler,
    create_remove_series_candidates_handler,
    create_replace_series_candidates_handler,
    create_view_series_candidates_handler,
)
from backend.agent.tools.video import OPEN_VIDEO_TOOL, VIDEO_SEEK_TOOL, execute_open_video, execute_video_seek


BUSINESS_READ_TOOL_DEFINITIONS: list[ToolDefinition] = [
    LIST_SERIES_VIDEOS_TOOL,
    GET_VIDEO_SUMMARY_TOOL,
    GET_VIDEO_TOOLS_TOOL,
    GET_VIDEO_TRANSCRIPT_TOOL,
]

RUNTIME_INTERNAL_TOOL_DEFINITIONS: list[ToolDefinition] = [
    VIEW_SERIES_CANDIDATES_TOOL,
    ADD_SERIES_CANDIDATES_TOOL,
    REMOVE_SERIES_CANDIDATES_TOOL,
    REPLACE_SERIES_CANDIDATES_TOOL,
    CLEAR_SERIES_CANDIDATES_TOOL,
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
    *RUNTIME_INTERNAL_TOOL_DEFINITIONS,
    *UI_ACTION_TOOL_DEFINITIONS,
]

MODEL_VISIBLE_TOOL_PLANES: tuple[ToolPlane, ...] = (
    ToolPlane.BUSINESS_READ,
    ToolPlane.UI_ACTION,
)

TOOL_DEFINITIONS_BY_NAME: dict[ToolName, ToolDefinition] = {
    tool.name: tool
    for tool in ALL_TOOL_DEFINITIONS
}


def list_tool_definitions_for_context(context: AgentContext) -> list[ToolDefinition]:
    allowed_contexts = _resolve_tool_context_tags(context)
    return [
        tool
        for tool in ALL_TOOL_DEFINITIONS
        if any(tag in allowed_contexts for tag in tool.contexts)
    ]


def get_tool_definition(tool_name: ToolName) -> ToolDefinition:
    return TOOL_DEFINITIONS_BY_NAME[tool_name]


def list_tool_definitions_for_plane(plane: ToolPlane) -> list[ToolDefinition]:
    return [
        tool
        for tool in ALL_TOOL_DEFINITIONS
        if tool.plane == plane
    ]


def list_model_visible_tool_definitions_for_context(context: AgentContext) -> list[ToolDefinition]:
    return [
        tool
        for tool in list_tool_definitions_for_context(context)
        if tool.plane in MODEL_VISIBLE_TOOL_PLANES
    ]


def tool_is_model_visible(tool_name: ToolName) -> bool:
    return get_tool_definition(tool_name).plane in MODEL_VISIBLE_TOOL_PLANES


def list_tool_names_for_intent(intent_tag: ToolIntentTag) -> set[ToolName]:
    return {
        tool.name
        for tool in ALL_TOOL_DEFINITIONS
        if intent_tag in tool.intents
    }


def tool_is_available_in_context(tool_name: ToolName, context: AgentContext) -> bool:
    tool = get_tool_definition(tool_name)
    allowed_contexts = _resolve_tool_context_tags(context)
    return any(tag in allowed_contexts for tag in tool.contexts)


def tool_requires_candidate_buffer(tool_name: ToolName) -> bool:
    return get_tool_definition(tool_name).requires_candidate_buffer


def tool_requires_video_id(tool_name: ToolName) -> bool:
    return get_tool_definition(tool_name).requires_video_id


def tool_has_effect(tool_name: ToolName, effect: ToolEffectTag) -> bool:
    return effect in get_tool_definition(tool_name).effects


def tool_is_concurrency_safe(tool_name: ToolName) -> bool:
    return get_tool_definition(tool_name).concurrency_safe


def _resolve_tool_context_tags(context: AgentContext) -> tuple[ToolContextTag, ...]:
    if context.scope_type == "video":
        return (ToolContextTag.VIDEO,)
    if context.inspection_stage == InspectionStage.SERIES_DISCOVERY:
        return (ToolContextTag.SERIES_DISCOVERY,)
    return (
        ToolContextTag.SERIES_DISCOVERY,
        ToolContextTag.SERIES_INSPECTION,
    )


__all__ = [
    "create_add_series_candidates_handler",
    "create_clear_series_candidates_handler",
    "execute_generate_mindmap",
    "execute_open_knowledge_cards",
    "execute_open_mindmap",
    "execute_open_notes",
    "execute_generate_overview",
    "execute_open_overview",
    "execute_open_series_home",
    "execute_open_series_overview",
    "create_remove_series_candidates_handler",
    "create_replace_series_candidates_handler",
    "execute_save_note",
    "execute_open_video",
    "create_get_video_transcript_handler",
    "create_view_series_candidates_handler",
    "execute_video_seek",
    "BUSINESS_READ_TOOL_DEFINITIONS",
    "get_tool_definition",
    "list_model_visible_tool_definitions_for_context",
    "list_tool_definitions_for_plane",
    "list_tool_definitions_for_context",
    "list_tool_names_for_intent",
    "MODEL_VISIBLE_TOOL_PLANES",
    "RUNTIME_INTERNAL_TOOL_DEFINITIONS",
    "tool_has_effect",
    "tool_is_available_in_context",
    "tool_is_concurrency_safe",
    "tool_is_model_visible",
    "tool_requires_candidate_buffer",
    "tool_requires_video_id",
    "UI_ACTION_TOOL_DEFINITIONS",
]
