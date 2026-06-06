from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class BilibiliUrlInfoDTO:
    url: str
    url_type: Literal["unknown"] = "unknown"


@dataclass(frozen=True)
class LibrarySeriesDTO:
    id: str
    title: str
    videos: list["LibraryVideoCardDTO"]
    is_linked: bool = False
    source_url: str = ""


@dataclass(frozen=True)
class LibraryVideoCardDTO:
    id: str
    title: str
    source_name: str
    processed: bool
    status: str
    is_linked: bool = False
    bilibili_bvid: str = ""
    bilibili_page: int = 0
    source_url: str = ""
    provider: str = ""


@dataclass(frozen=True)
class WorkspaceDTO:
    id: str
    title: str


@dataclass(frozen=True)
class VideoLibraryDTO:
    workspace: WorkspaceDTO
    series: list[LibrarySeriesDTO]


@dataclass(frozen=True)
class VideoSourceDTO:
    series_id: str
    video_id: str
    title: str
    source_name: str
    source_path: Path
    output_dir: Path
    processed: bool
    duration_seconds: float | None = None


@dataclass(frozen=True)
class VideoSummaryDTO:
    series_id: str
    video_id: str
    title: str
    summary: dict[str, Any]


@dataclass(frozen=True)
class TranscriptSegmentDTO:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class VideoTranscriptDTO:
    series_id: str
    video_id: str
    title: str
    duration_seconds: float | None
    segments: list[TranscriptSegmentDTO]


@dataclass(frozen=True)
class VideoMindmapDTO:
    series_id: str
    video_id: str
    title: str
    mindmap: dict[str, Any]


@dataclass(frozen=True)
class ChapterCardDTO:
    id: str
    title: str
    summary: str
    key_points: list[str]
    start_seconds: float | None
    end_seconds: float | None
    kind: str


@dataclass(frozen=True)
class VideoChapterCardsDTO:
    series_id: str
    video_id: str
    title: str
    cards: list[ChapterCardDTO]


@dataclass(frozen=True)
class KnowledgeCardDTO:
    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str]
    keywords: list[str]
    related_card_ids: list[str]


@dataclass(frozen=True)
class VideoKnowledgeCardsDTO:
    series_id: str
    video_id: str
    title: str
    cards: list[KnowledgeCardDTO]


@dataclass(frozen=True)
class VideoNoteDTO:
    id: str
    title: str
    content: str
    source: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class VideoNotesDTO:
    series_id: str
    video_id: str
    title: str
    notes: list[VideoNoteDTO]


@dataclass(frozen=True)
class WorkspaceToolDTO:
    id: str
    title: str
    available: bool
    generated: bool
    status: str
    preview_url: str | None = None


@dataclass(frozen=True)
class VideoWorkspaceToolsDTO:
    series_id: str
    video_id: str
    overview: WorkspaceToolDTO
    knowledge_cards: WorkspaceToolDTO
    mindmap: WorkspaceToolDTO
    notes: WorkspaceToolDTO
    preview: WorkspaceToolDTO
    ai_todo: str
