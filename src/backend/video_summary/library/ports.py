from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.domain.models import SummaryDocument
from backend.video_summary.library.views import KnowledgeCardView
from backend.video_summary.library.views import (
    VideoChapterCardsView,
    VideoKnowledgeCardsView,
    SeriesView,
    VideoLibraryView,
    VideoMindmapView,
    VideoNoteView,
    VideoNotesView,
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

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsView | None:
        ...

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsView | None:
        ...

    def save_video_knowledge_cards(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        cards: list[KnowledgeCardView],
    ) -> None:
        ...

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesView | None:
        ...

    def create_video_note(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        content: str,
        source: str,
    ) -> VideoNoteView | None:
        ...

    def update_video_note(
        self,
        series_id: str,
        video_id: str,
        note_id: str,
        *,
        title: str,
        content: str,
    ) -> VideoNoteView | None:
        ...

    def delete_video_note(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        ...

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsView | None:
        ...


class VideoSummaryGenerator(Protocol):
    async def run(
        self,
        source_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> SummaryDocument:
        ...


class VideoMindmapGenerator(Protocol):
    async def run(self, source_path: Path, output_dir: Path, summary_data: dict[str, object]) -> dict[str, object]:
        ...


class KnowledgeCardGenerator(Protocol):
    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardView]:
        ...


class VideoGenerationProgressTracker(Protocol):
    def create_reporter(self, task_id: str) -> ProgressReporter:
        ...
