from __future__ import annotations

from dataclasses import dataclass

from backend.video_summary.library.ports import VideoWorkspace, WorkspaceIndexInvalidator


@dataclass(frozen=True)
class DeleteSeriesResult:
    series_id: str


@dataclass(frozen=True)
class DeleteVideoResult:
    series_id: str
    video_id: str


class DeleteSeries:
    def __init__(self, workspace: VideoWorkspace, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, series_id: str) -> DeleteSeriesResult:
        deleted = self._workspace.delete_series(series_id)
        if not deleted:
            raise LookupError(f"series not found '{series_id}'")
        self._invalidator.invalidate()
        return DeleteSeriesResult(series_id=series_id)


class DeleteVideoSource:
    def __init__(self, workspace: VideoWorkspace, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, series_id: str, video_id: str) -> DeleteVideoResult:
        deleted = self._workspace.delete_video(series_id, video_id)
        if not deleted:
            raise LookupError(f"video not found '{series_id}/{video_id}'")
        self._invalidator.invalidate()
        return DeleteVideoResult(series_id=series_id, video_id=video_id)


class DeleteLinkedSeries:
    def __init__(self, workspace: VideoWorkspace, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, series_id: str) -> DeleteSeriesResult:
        deleted = self._workspace.delete_linked_series(series_id)
        if not deleted:
            raise LookupError(f"linked series not found: {series_id}")
        self._invalidator.invalidate()
        return DeleteSeriesResult(series_id=series_id)
