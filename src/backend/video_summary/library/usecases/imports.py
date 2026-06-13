from __future__ import annotations

from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO
from backend.video_summary.library.ports import VideoImportStore


class ImportLocalSeries:
    def __init__(self, workspace: VideoImportStore) -> None:
        self._workspace = workspace

    def run(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        return self._workspace.import_local_series(title=title, files=files)


class ImportLocalPlaygroundVideos:
    def __init__(self, workspace: VideoImportStore) -> None:
        self._workspace = workspace

    def run(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        return self._workspace.import_local_playground_videos(files=files)


class ImportLocalSeriesVideos:
    def __init__(self, workspace: VideoImportStore) -> None:
        self._workspace = workspace

    def run(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        return self._workspace.import_local_series_videos(series_id=series_id, files=files)
