from __future__ import annotations

from backend.video_summary.library.models import VideoNoteDTO, VideoNotesDTO
from backend.video_summary.library.ports import VideoNotesStore, WorkspaceIndexRefresher


class GetVideoNotes:
    def __init__(self, workspace: VideoNotesStore) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        return self._workspace.get_video_notes(series_id, video_id)


class CreateVideoNote:
    def __init__(self, workspace: VideoNotesStore, index_refresher: WorkspaceIndexRefresher | None = None) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, *, title: str, content: str, source: str) -> VideoNoteDTO | None:
        note = self._workspace.create_video_note(
            series_id,
            video_id,
            title=title,
            content=content,
            source=source,
        )
        if note is not None and self._index_refresher is not None:
            self._index_refresher.refresh()
        return note


class UpdateVideoNote:
    def __init__(self, workspace: VideoNotesStore, index_refresher: WorkspaceIndexRefresher | None = None) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, note_id: str, *, title: str, content: str) -> VideoNoteDTO | None:
        note = self._workspace.update_video_note(
            series_id,
            video_id,
            note_id,
            title=title,
            content=content,
        )
        if note is not None and self._index_refresher is not None:
            self._index_refresher.refresh()
        return note


class DeleteVideoNote:
    def __init__(self, workspace: VideoNotesStore, index_refresher: WorkspaceIndexRefresher | None = None) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        deleted = self._workspace.delete_video_note(series_id, video_id, note_id)
        if deleted and self._index_refresher is not None:
            self._index_refresher.refresh()
        return deleted
