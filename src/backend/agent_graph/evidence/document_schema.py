from __future__ import annotations

from pydantic import BaseModel, Field


class SeriesCatalogVideoRecord(BaseModel):
    video_id: str
    title: str
    one_sentence_summary: str = ""
    chapter_titles: list[str] = Field(default_factory=list)
    processed: bool = False


class SeriesCatalogPayload(BaseModel):
    series_id: str
    series_title: str
    videos: list[SeriesCatalogVideoRecord] = Field(default_factory=list)
    updated_at: str


class RetrievalDocumentRecord(BaseModel):
    doc_id: str
    series_id: str
    video_id: str = ""
    title: str = ""
    source_type: str
    source_family: str
    chapter_title: str = ""
    start_seconds: float | None = None
    end_seconds: float | None = None
    note_id: str = ""
    note_source: str = ""
    card_id: str = ""
    card_kind: str = ""
    text: str
