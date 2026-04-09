from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ToolAvailability(BaseModel):
    available: bool = False
    generated: bool = False
    status: str = "idle"


class InspectionStage(str, Enum):
    SERIES_DISCOVERY = "series_discovery"
    VIDEO_INSPECTION = "video_inspection"
    ANSWER_READY = "answer_ready"


class AgentContext(BaseModel):
    session_id: str
    workspace_title: str = "Video Include"
    scope_type: str = "series"
    series_id: str | None = None
    series_title: str | None = None
    video_id: str | None = None
    video_title: str | None = None
    selected_tool: str | None = None
    overview: ToolAvailability = Field(default_factory=ToolAvailability)
    mindmap: ToolAvailability = Field(default_factory=ToolAvailability)
    knowledge_cards: ToolAvailability = Field(default_factory=ToolAvailability)
    notes: ToolAvailability = Field(default_factory=ToolAvailability)
    preview: ToolAvailability = Field(default_factory=ToolAvailability)
    inspection_stage: InspectionStage = InspectionStage.SERIES_DISCOVERY
    chapter_titles: list[str] = Field(default_factory=list)
    recent_messages: list[str] = Field(default_factory=list)
