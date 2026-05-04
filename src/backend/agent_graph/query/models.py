from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CompareSplitDecision(BaseModel):
    queries: list[str] = Field(default_factory=list)
    reason: str = ""


class QueryPlanningInput(BaseModel):
    scope_type: str
    series_id: str = ""
    video_id: str = ""
    user_message: str = ""
    history_selected_videos: list[dict[str, object]] = Field(default_factory=list)


class SelectionMode(str, Enum):
    FRESH = "fresh"
    CARRY_FORWARD = "carry_forward"


class ExecutionDepth(str, Enum):
    SERIES_META = "series_meta"
    SUMMARY = "summary"
    VIDEO_GRAPH = "video_graph"
    VIDEO_WORKFLOW = "video_workflow"
    VIDEO_RAG = "video_rag"


class SelectedVideo(BaseModel):
    video_id: str
    reason_for_selection: str = ""


class QuerySubplan(BaseModel):
    target_video_ids: list[str] = Field(default_factory=list)
    depth: ExecutionDepth
    query: str
    retrieval_tags: list[str] = Field(default_factory=list)


class StructuredQueryPlan(BaseModel):
    goal: str
    target_source: str
    context_need: str
    reason: str = ""
    action_name: str = ""
    action_args: dict[str, object] = Field(default_factory=dict)
    candidate_video_ids: list[str] = Field(default_factory=list)
    selected_videos: list[SelectedVideo] = Field(default_factory=list)
    selection_mode: SelectionMode = SelectionMode.FRESH
    retrieval_tags: list[str] = Field(default_factory=list)
    subplans: list[QuerySubplan] = Field(default_factory=list)


class SeriesQueryUnderstanding(BaseModel):
    normalized_query: str
    subqueries: list[str] = Field(default_factory=list)
    filters: dict[str, object] = Field(default_factory=dict)


class RetrievalHit(BaseModel):
    evidence_id: str
    doc_id: str
    series_id: str
    video_id: str | None = None
    source_type: str
    source_family: str
    title: str
    chapter_title: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    score: float = 0.0
    text: str = ""


class SeriesAnswerPayload(BaseModel):
    answer: str
    citations: list[dict[str, object]] = Field(default_factory=list)
    used_source_types: list[str] = Field(default_factory=list)
