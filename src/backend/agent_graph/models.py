from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    task_id: str
    instruction: str
    depends_on: list[str] = Field(default_factory=list)
    kind_hint: str = ""


class DecomposeDecision(BaseModel):
    tasks: list[AgentTask] = Field(default_factory=list)
    reason: str = ""


class CompareSplitDecision(BaseModel):
    queries: list[str] = Field(default_factory=list)
    reason: str = ""


class SelectionMode(str, Enum):
    FRESH = "fresh"
    CARRY_FORWARD = "carry_forward"


class ExecutionDepth(str, Enum):
    SERIES_META = "series_meta"
    SUMMARY = "summary"
    VIDEO_GRAPH = "video_graph"
    VIDEO_WORKFLOW = "video_workflow"


class SelectedVideo(BaseModel):
    video_id: str
    reason_for_selection: str = ""
    needs_probe: bool = False


class QuerySubplan(BaseModel):
    target_video_ids: list[str] = Field(default_factory=list)
    depth: ExecutionDepth
    query: str
    needs_probe: bool = False


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
    subplans: list[QuerySubplan] = Field(default_factory=list)


class SeriesQueryDecision(BaseModel):
    goal: str
    target_source: str
    context_need: str
    reason: str = ""
    action_name: str = ""
    action_args: dict[str, object] = Field(default_factory=dict)
    candidate_video_ids: list[str] = Field(default_factory=list)
    selected_videos: list[SelectedVideo] = Field(default_factory=list)
    selection_mode: SelectionMode = SelectionMode.FRESH
    subplans: list[QuerySubplan] = Field(default_factory=list)
