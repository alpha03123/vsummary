from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkspaceView:
    id: str
    title: str


@dataclass(frozen=True)
class SeriesView:
    id: str
    title: str


@dataclass(frozen=True)
class VideoCardView:
    id: str
    title: str


@dataclass(frozen=True)
class VideoLibraryView:
    workspace: WorkspaceView
    series: SeriesView
    videos: list[VideoCardView]


@dataclass(frozen=True)
class VideoSummaryView:
    video_id: str
    title: str
    summary: dict[str, Any]
