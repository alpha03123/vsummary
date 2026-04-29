from __future__ import annotations

from backend.video_summary.library.models import VideoNoteDTO, VideoNotesDTO
from backend.video_summary.library.ports import VideoWorkspace


class GetVideoNotes:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        return self._workspace.get_video_notes(series_id, video_id)


class CreateVideoNote:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str, *, title: str, content: str, source: str) -> VideoNoteDTO | None:
        return self._workspace.create_video_note(
            series_id,
            video_id,
            title=title,
            content=content,
            source=source,
        )


class UpdateVideoNote:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str, note_id: str, *, title: str, content: str) -> VideoNoteDTO | None:
        return self._workspace.update_video_note(
            series_id,
            video_id,
            note_id,
            title=title,
            content=content,
        )


class DeleteVideoNote:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        return self._workspace.delete_video_note(series_id, video_id, note_id)
