from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ToolName(str, Enum):
    LIST_SERIES_VIDEOS = "list_series_videos"
    GET_VIDEO_SUMMARY = "get_video_summary"
    GET_VIDEO_TOOLS = "get_video_tools"
    GET_VIDEO_TRANSCRIPT = "get_video_transcript"
    OPEN_SERIES_HOME = "open_series_home"
    OPEN_SERIES_OVERVIEW = "open_series_overview"
    OPEN_OVERVIEW = "open_overview"
    OPEN_MINDMAP = "open_mindmap"
    OPEN_KNOWLEDGE_CARDS = "open_knowledge_cards"
    OPEN_NOTES = "open_notes"
    OPEN_VIDEO = "open_video"
    VIDEO_SEEK = "video_seek"
    GENERATE_OVERVIEW = "generate_overview"
    GENERATE_MINDMAP = "generate_mindmap"
    SAVE_NOTE = "save_note"


class ToolContextTag(str, Enum):
    SERIES = "series"
    VIDEO = "video"


class ToolPlane(str, Enum):
    BUSINESS_READ = "business_read"
    UI_ACTION = "ui_action"


class ToolDefinition(BaseModel):
    name: ToolName
    title: str
    description: str
    plane: ToolPlane
    arguments: dict[str, str] = Field(default_factory=dict)
    contexts: tuple[ToolContextTag, ...] = ()


class ListSeriesVideosCall(BaseModel):
    tool_name: Literal[ToolName.LIST_SERIES_VIDEOS] = ToolName.LIST_SERIES_VIDEOS
    series_id: str | None = None


class GetVideoSummaryCall(BaseModel):
    tool_name: Literal[ToolName.GET_VIDEO_SUMMARY] = ToolName.GET_VIDEO_SUMMARY
    series_id: str | None = None
    video_id: str | None = None


class GetVideoToolsCall(BaseModel):
    tool_name: Literal[ToolName.GET_VIDEO_TOOLS] = ToolName.GET_VIDEO_TOOLS
    series_id: str | None = None
    video_id: str | None = None


class GetVideoTranscriptCall(BaseModel):
    tool_name: Literal[ToolName.GET_VIDEO_TRANSCRIPT] = ToolName.GET_VIDEO_TRANSCRIPT
    series_id: str | None = None
    video_id: str | None = None


class OpenSeriesHomeCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_SERIES_HOME] = ToolName.OPEN_SERIES_HOME


class OpenSeriesOverviewCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_SERIES_OVERVIEW] = ToolName.OPEN_SERIES_OVERVIEW


class OpenOverviewCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_OVERVIEW] = ToolName.OPEN_OVERVIEW


class OpenMindmapCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_MINDMAP] = ToolName.OPEN_MINDMAP


class OpenKnowledgeCardsCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_KNOWLEDGE_CARDS] = ToolName.OPEN_KNOWLEDGE_CARDS


class OpenVideoCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_VIDEO] = ToolName.OPEN_VIDEO


class OpenNotesCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_NOTES] = ToolName.OPEN_NOTES


class VideoSeekCall(BaseModel):
    tool_name: Literal[ToolName.VIDEO_SEEK] = ToolName.VIDEO_SEEK
    seek_seconds: float
    match_end_seconds: float | None = None
    matched_text: str = ""
    chapter_title: str = ""
    query: str = ""


class GenerateOverviewCall(BaseModel):
    tool_name: Literal[ToolName.GENERATE_OVERVIEW] = ToolName.GENERATE_OVERVIEW


class GenerateMindmapCall(BaseModel):
    tool_name: Literal[ToolName.GENERATE_MINDMAP] = ToolName.GENERATE_MINDMAP


class SaveNoteCall(BaseModel):
    tool_name: Literal[ToolName.SAVE_NOTE] = ToolName.SAVE_NOTE
    note_title: str
    note_content: str


ToolCall = Annotated[
    ListSeriesVideosCall
    | GetVideoSummaryCall
    | GetVideoToolsCall
    | GetVideoTranscriptCall
    | OpenSeriesHomeCall
    | OpenSeriesOverviewCall
    | OpenOverviewCall
    | OpenMindmapCall
    | OpenKnowledgeCardsCall
    | OpenNotesCall
    | OpenVideoCall
    | VideoSeekCall
    | GenerateOverviewCall
    | GenerateMindmapCall
    | SaveNoteCall,
    Field(discriminator="tool_name"),
]


class ToolExecutionResult(BaseModel):
    tool_name: ToolName
    status: str
    payload: dict[str, object] = Field(default_factory=dict)
