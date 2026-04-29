from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.domain.models import SummaryDocument
from backend.video_summary.library.models import (
    BilibiliUrlInfoDTO,
    KnowledgeCardDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoChapterCardsDTO,
    VideoKnowledgeCardsDTO,
    VideoMindmapDTO,
    VideoNoteDTO,
    VideoNotesDTO,
    VideoSourceDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
    VideoWorkspaceToolsDTO,
    WorkspaceDTO,
)
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


class VideoWorkspace(Protocol):
    def get_workspace(self) -> WorkspaceDTO:
        ...

    def list_series(self) -> list[LibrarySeriesDTO]:
        ...

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        ...

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        ...

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        ...

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        ...

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        ...

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        ...

    def save_video_knowledge_cards(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        cards: list[KnowledgeCardDTO],
    ) -> None:
        ...

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        ...

    def create_video_note(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        content: str,
        source: str,
    ) -> VideoNoteDTO | None:
        ...

    def update_video_note(
        self,
        series_id: str,
        video_id: str,
        note_id: str,
        *,
        title: str,
        content: str,
    ) -> VideoNoteDTO | None:
        ...

    def delete_video_note(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        ...

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        ...

    def import_local_series(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        ...

    def import_local_playground_videos(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        ...

    def import_local_series_videos(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        ...

    def delete_series(self, series_id: str) -> bool:
        ...

    def delete_video(self, series_id: str, video_id: str) -> bool:
        ...

    def save_linked_series(self, series: LinkedSeries) -> None:
        ...

    def get_linked_series(self, series_id: str) -> LinkedSeries | None:
        ...

    def delete_linked_series(self, series_id: str, *, delete_videos: bool = False) -> bool:
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
    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardDTO]:
        ...


class VideoGenerationProgressTracker(Protocol):
    def create_reporter(self, task_id: str) -> ProgressReporter:
        ...


class WorkspaceIndexInvalidator(Protocol):
    def invalidate(self) -> None:
        ...


class LinkedVideoResolver(Protocol):
    async def resolve_series(self, url_info: BilibiliUrlInfoDTO) -> LinkedSeries:
        ...

    async def resolve_single_video(self, url_info: BilibiliUrlInfoDTO) -> LinkedVideo:
        ...


class BilibiliUrlParser(Protocol):
    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        ...


class LinkedVideoDownloadStarter(Protocol):
    def start(self, *, series_id: str, video_id: str, bvid: str, page: int) -> str:
        ...
