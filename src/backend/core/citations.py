"""Public citation contracts shared by video and Agent capabilities."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
