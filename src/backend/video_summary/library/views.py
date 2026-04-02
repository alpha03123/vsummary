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


@dataclass(frozen=True)
class VideoCardView:
    id: str
    title: str
    source_name: str
    processed: bool
    status: str


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
class VideoSourceView:
    series_id: str
    video_id: str
    title: str
    source_name: str
    source_path: Path
    output_dir: Path
    processed: bool
