from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult


class ScopeType(str, Enum):
    SERIES = "series"
    VIDEO = "video"


class AgentActionPlan(BaseModel):
    scope_type: ScopeType
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reason: str = ""
    use_answerer: bool = False


class CitationSlot(BaseModel):
    slot: int
    target_type: str
    series_id: str | None = None
    video_id: str | None = None
    video_title: str | None = None
    chapter_id: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str | None = None
    url: str | None = None
    candidates: list["CitationSlotCandidate"] = Field(default_factory=list)


class CitationSlotCandidate(BaseModel):
    start_seconds: float | None = None
    end_seconds: float | None = None
    text: str | None = None


class CitationReference(BaseModel):
    id: str
    label: str
    source_type: str
    search_scope: str
    slots: list[CitationSlot] = Field(default_factory=list)


class AgentTurnResult(BaseModel):
    assistant_message: str
    plan: AgentActionPlan
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
    citations: list[CitationReference] = Field(default_factory=list)
