from __future__ import annotations

from pydantic import BaseModel, Field


class ToolAvailability(BaseModel):
    available: bool = False
    generated: bool = False
    status: str = "idle"


class AgentContext(BaseModel):
    session_id: str
    workspace_title: str = "Video Include"
    scope_type: str = "library"
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
    chapter_titles: list[str] = Field(default_factory=list)
    recent_messages: list[str] = Field(default_factory=list)
