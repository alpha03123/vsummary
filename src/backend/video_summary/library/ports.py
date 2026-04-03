from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.domain.models import SummaryDocument
from backend.video_summary.library.views import (
    SeriesView,
    VideoLibraryView,
    VideoMindmapView,
    VideoSourceView,
    VideoSummaryView,
    VideoWorkspaceToolsView,
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

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapView | None:
        ...

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsView | None:
        ...


class VideoSummaryGenerator(Protocol):
    def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> SummaryDocument:
        ...


class VideoMindmapGenerator(Protocol):
    def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object]) -> dict[str, object]:
        ...


class VideoGenerationProgressTracker(Protocol):
    def create_reporter(self, task_id: str) -> ProgressReporter:
        ...
