from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkspaceView:
    id: str
    title: str


@dataclass(frozen=True)
class SeriesView:
    id: str
    title: str
    videos: list["VideoCardView"]
    is_linked: bool = False
    source_url: str = ""


@dataclass(frozen=True)
class VideoCardView:
    id: str
    title: str
    source_name: str
    processed: bool
    status: str
    is_linked: bool = False
    bilibili_bvid: str = ""
    bilibili_page: int = 0
    source_url: str = ""


@dataclass(frozen=True)
class VideoLibraryView:
    workspace: WorkspaceView
    series: list[SeriesView]


@dataclass(frozen=True)
class VideoSummaryView:
    series_id: str
    video_id: str
    title: str
    summary: dict[str, Any]


@dataclass(frozen=True)
class TranscriptSegmentView:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class VideoTranscriptView:
    series_id: str
    video_id: str
    title: str
    duration_seconds: float | None
    segments: list[TranscriptSegmentView]


@dataclass(frozen=True)
class VideoMindmapView:
    series_id: str
    video_id: str
    title: str
    mindmap: dict[str, Any]


@dataclass(frozen=True)
class ChapterCardView:
    id: str
    title: str
    summary: str
    key_points: list[str]
    start_seconds: float | None
    end_seconds: float | None
    kind: str


@dataclass(frozen=True)
class VideoChapterCardsView:
    series_id: str
    video_id: str
    title: str
    cards: list[ChapterCardView]


@dataclass(frozen=True)
class KnowledgeCardSourceRefView:
    chapter_id: str | None
    start_seconds: float | None
    end_seconds: float | None
    quote: str


@dataclass(frozen=True)
class KnowledgeCardView:
    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str]
    keywords: list[str]
    source_refs: list[KnowledgeCardSourceRefView]
    related_card_ids: list[str]


@dataclass(frozen=True)
class VideoKnowledgeCardsView:
    series_id: str
    video_id: str
    title: str
    cards: list[KnowledgeCardView]


@dataclass(frozen=True)
class VideoNoteView:
    id: str
    title: str
    content: str
    source: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class VideoNotesView:
    series_id: str
    video_id: str
    title: str
    notes: list[VideoNoteView]


@dataclass(frozen=True)
class WorkspaceToolView:
    id: str
    title: str
    available: bool
    generated: bool
    status: str
    preview_url: str | None = None


@dataclass(frozen=True)
class VideoWorkspaceToolsView:
    series_id: str
    video_id: str
    overview: WorkspaceToolView
    knowledge_cards: WorkspaceToolView
    mindmap: WorkspaceToolView
    notes: WorkspaceToolView
    preview: WorkspaceToolView
    ai_todo: str


@dataclass(frozen=True)
class VideoSourceView:
    series_id: str
    video_id: str
    title: str
    source_name: str
    source_path: Path
    output_dir: Path
    processed: bool
    duration_seconds: float | None = None
