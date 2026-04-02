from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.video_summary.domain.models import SummaryDocument
from backend.video_summary.library.views import (
    SeriesView,
    VideoLibraryView,
    VideoSourceView,
    VideoSummaryView,
    WorkspaceView,
)


class VideoWorkspace(Protocol):
    def get_workspace(self) -> WorkspaceView:
        ...

    def list_series(self) -> list[SeriesView]:
        ...

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceView | None:
        ...

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryView | None:
        ...


class VideoSummaryGenerator(Protocol):
    def run(self, source_path: Path, output_dir: Path) -> SummaryDocument:
        ...
