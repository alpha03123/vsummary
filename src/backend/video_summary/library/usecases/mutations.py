from __future__ import annotations

from dataclasses import dataclass

from backend.video_summary.library.ports import (
    GenerationActivityChecker,
    VideoMutationStore,
    WorkspaceIndexRefresher,
)


@dataclass(frozen=True)
class DeleteSeriesResult:
    series_id: str


@dataclass(frozen=True)
class DeleteVideoResult:
    series_id: str
    video_id: str


class GenerationInProgressError(RuntimeError):
    pass


class DeleteSeries:
    def __init__(
        self,
        workspace: VideoMutationStore,
        index_refresher: WorkspaceIndexRefresher,
        generation_activity_checker: GenerationActivityChecker | None = None,
    ) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher
        self._generation_activity_checker = generation_activity_checker

    def run(self, series_id: str) -> DeleteSeriesResult:
        if (
            self._generation_activity_checker is not None
            and self._generation_activity_checker.is_series_generation_active(series_id)
        ):
            raise GenerationInProgressError(f"系列 '{series_id}' 正在生成，请先取消生成后再删除。")
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        processed_exists = bool(series and any(video.processed for video in series.videos))
        deleted = self._workspace.delete_series(series_id)
        if not deleted:
            raise LookupError(f"series not found '{series_id}'")
        if processed_exists:
            self._index_refresher.delete_series(series_id)
        return DeleteSeriesResult(series_id=series_id)


class DeleteVideoSource:
    def __init__(
        self,
        workspace: VideoMutationStore,
        index_refresher: WorkspaceIndexRefresher,
        generation_activity_checker: GenerationActivityChecker | None = None,
    ) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher
        self._generation_activity_checker = generation_activity_checker

    def run(self, series_id: str, video_id: str) -> DeleteVideoResult:
        if (
            self._generation_activity_checker is not None
            and self._generation_activity_checker.is_video_generation_active(series_id, video_id)
        ):
            raise GenerationInProgressError(f"视频 '{series_id}/{video_id}' 正在生成，请先取消生成后再删除。")
        source = self._workspace.get_video_source(series_id, video_id)
        processed = bool(source and source.processed)
        deleted = self._workspace.delete_video(series_id, video_id)
        if not deleted:
            raise LookupError(f"video not found '{series_id}/{video_id}'")
        if processed:
            self._index_refresher.delete_video(series_id, video_id)
        return DeleteVideoResult(series_id=series_id, video_id=video_id)
