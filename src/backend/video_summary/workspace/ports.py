from __future__ import annotations

from typing import Protocol

from backend.video_summary.workspace.models import (
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
from backend.video_summary.workspace.linked_models import LinkedSeries, LinkedVideo


class VideoLibraryReader(Protocol):
    def get_workspace(self) -> WorkspaceDTO:
        ...

    def list_series(self) -> list[LibrarySeriesDTO]:
        ...

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        ...

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        ...

    def get_series_catalog(self, series_id: str) -> dict[str, object] | None:
        ...

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        ...

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        ...

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        ...

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        ...

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        ...

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        ...


class VideoKnowledgeCardWriter(Protocol):
    def save_video_knowledge_cards(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        cards: list[KnowledgeCardDTO],
    ) -> None:
        ...

class VideoKnowledgeCardStore(VideoLibraryReader, VideoKnowledgeCardWriter, Protocol):
    pass


class VideoKnowledgeCardStoreWithRefresh(VideoKnowledgeCardStore, Protocol):
    pass


class VideoNotesStore(Protocol):
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

class VideoImportStore(Protocol):
    def import_local_series(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        ...

    def import_local_playground_videos(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        ...

    def import_local_series_videos(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        ...


class VideoMutationStore(Protocol):
    def list_series(self) -> list[LibrarySeriesDTO]:
        ...

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        ...

    def delete_series(self, series_id: str) -> bool:
        ...

    def delete_video(self, series_id: str, video_id: str) -> bool:
        ...


class LinkedSeriesStore(Protocol):
    def save_linked_series(self, series: LinkedSeries) -> None:
        ...

    def get_linked_series(self, series_id: str) -> LinkedSeries | None:
        ...

    def delete_linked_series(self, series_id: str) -> bool:
        ...


class LinkedSeriesResolverWorkspace(VideoLibraryReader, LinkedSeriesStore, Protocol):
    pass
