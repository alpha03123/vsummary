from __future__ import annotations

from pydantic import BaseModel, Field


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
    citations: list[str] = Field(default_factory=list, description="使用到的 retrieval_hits evidence_id 列表。")
    used_source_types: list[str] = Field(default_factory=list)
