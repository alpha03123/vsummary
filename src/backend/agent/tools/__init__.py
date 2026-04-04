from backend.agent.tools.mindmap import MINDMAP_TOOL, execute_generate_mindmap
from backend.agent.tools.notes import OPEN_NOTES_TOOL, SAVE_NOTE_TOOL, execute_open_notes, execute_save_note
from backend.agent.tools.overview import (
    GENERATE_OVERVIEW_TOOL,
    OPEN_OVERVIEW_TOOL,
    execute_generate_overview,
    execute_open_overview,
)
from backend.agent.tools.series import OPEN_SERIES_HOME_TOOL, execute_open_series_home
from backend.agent.tools.transcript import TRANSCRIPT_LOOKUP_TOOL, create_transcript_lookup_handler
from backend.agent.tools.video import OPEN_VIDEO_TOOL, VIDEO_SEEK_TOOL, execute_open_video, execute_video_seek


def list_tool_definitions():
    return [
        OPEN_SERIES_HOME_TOOL,
        OPEN_OVERVIEW_TOOL,
        OPEN_NOTES_TOOL,
        GENERATE_OVERVIEW_TOOL,
        MINDMAP_TOOL,
        OPEN_VIDEO_TOOL,
        VIDEO_SEEK_TOOL,
        SAVE_NOTE_TOOL,
        TRANSCRIPT_LOOKUP_TOOL,
    ]


__all__ = [
    "execute_generate_mindmap",
    "execute_open_notes",
    "execute_generate_overview",
    "execute_open_overview",
    "execute_open_series_home",
    "execute_save_note",
    "execute_open_video",
    "create_transcript_lookup_handler",
    "execute_video_seek",
    "list_tool_definitions",
]
