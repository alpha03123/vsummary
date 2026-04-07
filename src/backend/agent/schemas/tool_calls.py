from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ToolName(str, Enum):
    LIST_SERIES_VIDEOS = "list_series_videos"
    VIEW_SERIES_CANDIDATES = "view_series_candidates"
    ADD_SERIES_CANDIDATES = "add_series_candidates"
    REMOVE_SERIES_CANDIDATES = "remove_series_candidates"
    REPLACE_SERIES_CANDIDATES = "replace_series_candidates"
    CLEAR_SERIES_CANDIDATES = "clear_series_candidates"
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
    SERIES_DISCOVERY = "series_discovery"
    SERIES_INSPECTION = "series_inspection"
    VIDEO = "video"


class ToolIntentTag(str, Enum):
    ANSWER_QUESTION = "answer_question"
    SERIES_ANSWER = "series_answer"
    OPEN_TOOL = "open_tool"
    SEEK_VIDEO = "seek_video"
    GENERATE_OVERVIEW = "generate_overview"
    GENERATE_MINDMAP = "generate_mindmap"


class ToolEffectTag(str, Enum):
    APPLY_CANDIDATE_BUFFER_PAYLOAD = "apply_candidate_buffer_payload"
    MARK_VIDEO_INSPECTED = "mark_video_inspected"


class ToolDefinition(BaseModel):
    name: ToolName
    title: str
    description: str
    arguments: dict[str, str] = Field(default_factory=dict)
    batch_tag: str | None = None
    contexts: tuple[ToolContextTag, ...] = ()
    intents: tuple[ToolIntentTag, ...] = ()
    effects: tuple[ToolEffectTag, ...] = ()
    requires_video_id: bool = False
    requires_candidate_buffer: bool = False


class ListSeriesVideosCall(BaseModel):
    tool_name: Literal[ToolName.LIST_SERIES_VIDEOS] = ToolName.LIST_SERIES_VIDEOS
    series_id: str | None = None


class ViewSeriesCandidatesCall(BaseModel):
    tool_name: Literal[ToolName.VIEW_SERIES_CANDIDATES] = ToolName.VIEW_SERIES_CANDIDATES


class AddSeriesCandidatesCall(BaseModel):
    tool_name: Literal[ToolName.ADD_SERIES_CANDIDATES] = ToolName.ADD_SERIES_CANDIDATES
    video_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class RemoveSeriesCandidatesCall(BaseModel):
    tool_name: Literal[ToolName.REMOVE_SERIES_CANDIDATES] = ToolName.REMOVE_SERIES_CANDIDATES
    video_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class ReplaceSeriesCandidatesCall(BaseModel):
    tool_name: Literal[ToolName.REPLACE_SERIES_CANDIDATES] = ToolName.REPLACE_SERIES_CANDIDATES
    video_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class ClearSeriesCandidatesCall(BaseModel):
    tool_name: Literal[ToolName.CLEAR_SERIES_CANDIDATES] = ToolName.CLEAR_SERIES_CANDIDATES


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
    | ViewSeriesCandidatesCall
    | AddSeriesCandidatesCall
    | RemoveSeriesCandidatesCall
    | ReplaceSeriesCandidatesCall
    | ClearSeriesCandidatesCall
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
