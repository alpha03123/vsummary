from __future__ import annotations

from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO
from backend.video_summary.library.ports import VideoImportStore, WorkspaceIndexInvalidator


class ImportLocalSeries:
    def __init__(self, workspace: VideoImportStore, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        series = self._workspace.import_local_series(title=title, files=files)
        self._invalidator.invalidate()
        return series


class ImportLocalPlaygroundVideos:
    def __init__(self, workspace: VideoImportStore, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        videos = self._workspace.import_local_playground_videos(files=files)
        self._invalidator.invalidate()
        return videos


class ImportLocalSeriesVideos:
    def __init__(self, workspace: VideoImportStore, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        videos = self._workspace.import_local_series_videos(series_id=series_id, files=files)
        self._invalidator.invalidate()
        return videos
