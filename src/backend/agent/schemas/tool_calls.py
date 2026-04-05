from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ToolName(str, Enum):
    LIST_SERIES_VIDEOS = "list_series_videos"
    GET_VIDEO_SUMMARY = "get_video_summary"
    GET_VIDEO_TOOLS = "get_video_tools"
    OPEN_SERIES_HOME = "open_series_home"
    OPEN_OVERVIEW = "open_overview"
    OPEN_MINDMAP = "open_mindmap"
    OPEN_KNOWLEDGE_CARDS = "open_knowledge_cards"
    OPEN_NOTES = "open_notes"
    OPEN_VIDEO = "open_video"
    VIDEO_SEEK = "video_seek"
    GENERATE_OVERVIEW = "generate_overview"
    GENERATE_MINDMAP = "generate_mindmap"
    SAVE_NOTE = "save_note"
    TRANSCRIPT_LOOKUP = "transcript_lookup"


class ToolDefinition(BaseModel):
    name: ToolName
    title: str
    description: str
    arguments: dict[str, str] = Field(default_factory=dict)


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


class OpenSeriesHomeCall(BaseModel):
    tool_name: Literal[ToolName.OPEN_SERIES_HOME] = ToolName.OPEN_SERIES_HOME


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


class GenerateOverviewCall(BaseModel):
    tool_name: Literal[ToolName.GENERATE_OVERVIEW] = ToolName.GENERATE_OVERVIEW


class GenerateMindmapCall(BaseModel):
    tool_name: Literal[ToolName.GENERATE_MINDMAP] = ToolName.GENERATE_MINDMAP


class SaveNoteCall(BaseModel):
    tool_name: Literal[ToolName.SAVE_NOTE] = ToolName.SAVE_NOTE
    note_title: str
    note_content: str


class TranscriptLookupCall(BaseModel):
    tool_name: Literal[ToolName.TRANSCRIPT_LOOKUP] = ToolName.TRANSCRIPT_LOOKUP
    query: str


ToolCall = Annotated[
    ListSeriesVideosCall
    | GetVideoSummaryCall
    | GetVideoToolsCall
    | OpenSeriesHomeCall
    | OpenOverviewCall
    | OpenMindmapCall
    | OpenKnowledgeCardsCall
    | OpenNotesCall
    | OpenVideoCall
    | VideoSeekCall
    | GenerateOverviewCall
    | GenerateMindmapCall
    | SaveNoteCall
    | TranscriptLookupCall,
    Field(discriminator="tool_name"),
]


class ToolExecutionResult(BaseModel):
    tool_name: ToolName
    status: str
    payload: dict[str, object] = Field(default_factory=dict)
