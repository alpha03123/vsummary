from __future__ import annotations

from pydantic import BaseModel, Field


class SummaryChapterPayload(BaseModel):
    id: str
    title: str
    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)


class SummaryPayload(BaseModel):
    title: str
    one_sentence_summary: str = ""
    core_problem: str = ""
    chapters: list[SummaryChapterPayload] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)


class MindmapNodePayload(BaseModel):
    id: str
    title: str
    summary: str = ""
    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    children: list["MindmapNodePayload"] = Field(default_factory=list)


class TranscriptSegmentPayload(BaseModel):
    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    text: str


class TranscriptEnhancementPayload(BaseModel):
    segments: list[TranscriptSegmentPayload] = Field(default_factory=list)
