from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from threading import Lock

from anyio import CapacityLimiter

from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.library.models import LibrarySeriesDTO
from backend.video_summary.library.models import VideoSummaryDTO
from backend.video_summary.library.ports import (
    SeriesKnowledgeMemoryRefresher,
    VideoGenerationProgressTracker,
    VideoLibraryReader,
    VideoSummaryGenerator,
)

LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class SeriesGenerationResult:
    series_id: str
    completed_videos: list[str]
    skipped_videos: list[str]
    cancelled_videos: list[str]
    cancelled_video_id: str | None = None


class DuplicateSeriesGenerationError(RuntimeError):
    pass


class GenerateVideoSummaryFromLibrary:
    def __init__(
        self,
        workspace: VideoLibraryReader,
        generator: VideoSummaryGenerator,
        progress_tracker: VideoGenerationProgressTracker,
        video_generation_concurrency: int = 1,
        series_memory_refresher: SeriesKnowledgeMemoryRefresher | None = None,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._progress_tracker = progress_tracker
        self._series_memory_refresher = series_memory_refresher
        self._active_tasks: dict[str, asyncio.Task[VideoSummaryDTO | None]] = {}
        self._active_tasks_lock = asyncio.Lock()
        self._active_task_keys: set[tuple[str, str]] = set()
        self._activity_lock = Lock()
        self._video_generation_slots = CapacityLimiter(max(1, video_generation_concurrency))

    def update_video_generation_concurrency(self, video_generation_concurrency: int) -> None:
        self._video_generation_slots.total_tokens = max(1, video_generation_concurrency)

    @property
    def generation_concurrency(self) -> int:
        return int(self._video_generation_slots.total_tokens)

    def is_video_generation_active(self, series_id: str, video_id: str) -> bool:
        with self._activity_lock:
            return (series_id, video_id) in self._active_task_keys

    def is_series_generation_active(self, series_id: str) -> bool:
        with self._activity_lock:
            return any(active_series_id == series_id for active_series_id, _ in self._active_task_keys)

    def get_active_video_ids(self, series_id: str) -> list[str]:
        with self._activity_lock:
            return [
                active_video_id
                for active_series_id, active_video_id in self._active_task_keys
                if active_series_id == series_id
            ]

    async def run(
        self,
        series_id: str,
        video_id: str,
        transcript_enhancement_enabled: bool | None = None,
        progress_reporter: ProgressReporter | None = None,
    ) -> VideoSummaryDTO | None:
        task_id = f"{series_id}/{video_id}"
        task = await self._get_or_create_task(
            task_id=task_id,
            series_id=series_id,
            video_id=video_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            progress_reporter=progress_reporter,
        )
        return await asyncio.shield(task)

    async def _get_or_create_task(
        self,
        *,
        task_id: str,
        series_id: str,
        video_id: str,
        transcript_enhancement_enabled: bool | None,
        progress_reporter: ProgressReporter | None,
    ) -> asyncio.Task[VideoSummaryDTO | None]:
        async with self._active_tasks_lock:
            existing = self._active_tasks.get(task_id)
            if existing is not None:
                return existing

            task = asyncio.create_task(
                self._run_generation(
                    task_id=task_id,
                    series_id=series_id,
                    video_id=video_id,
                    transcript_enhancement_enabled=transcript_enhancement_enabled,
                    progress_reporter=progress_reporter,
                )
            )
            self._active_tasks[task_id] = task
            with self._activity_lock:
                self._active_task_keys.add((series_id, video_id))
            return task

    async def _run_generation(
        self,
        *,
        task_id: str,
        series_id: str,
        video_id: str,
        transcript_enhancement_enabled: bool | None,
        progress_reporter: ProgressReporter | None,
    ) -> VideoSummaryDTO | None:
        reporter = progress_reporter or self._progress_tracker.create_reporter(f"{series_id}/{video_id}")
        try:
            if self._video_generation_slots.available_tokens <= 0:
                reporter.update("prepare", 0.0, "正在等待当前生成任务完成")

            async with self._video_generation_slots:
                await self._generator.run(
                    series_id=series_id,
                    video_id=video_id,
                    progress_reporter=reporter,
                    transcript_enhancement_enabled=transcript_enhancement_enabled,
                )
                if self._series_memory_refresher is not None:
                    try:
                        self._series_memory_refresher.refresh(series_id, video_id)
                    except Exception:
                        LOGGER.exception("series knowledge memory refresh failed for %s", series_id)
            reporter.completed("AI 概况已生成")
            return self._workspace.get_video_summary(series_id, video_id)
        except LookupError:
            return None
        except GenerateCancelledError:
            reporter.cancelled("AI 概况生成已取消")
            return None
        except RuntimeError as error:
            reporter.failed(str(error))
            raise
        except Exception as error:
            reporter.failed(str(error))
            raise RuntimeError(str(error)) from error
        finally:
            await self._clear_task(task_id)

    async def _clear_task(self, task_id: str) -> None:
        async with self._active_tasks_lock:
            current = self._active_tasks.get(task_id)
            if current is asyncio.current_task():
                self._active_tasks.pop(task_id, None)
                try:
                    series_id, video_id = task_id.split("/", 1)
                except ValueError:
                    return
                with self._activity_lock:
                    self._active_task_keys.discard((series_id, video_id))


class GenerateSeriesSummaryFromLibrary:
    def __init__(
        self,
        workspace: VideoLibraryReader,
        generator: GenerateVideoSummaryFromLibrary,
        progress_tracker: VideoGenerationProgressTracker,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._progress_tracker = progress_tracker
        self._active_series_tasks: dict[str, asyncio.Task[SeriesGenerationResult]] = {}
        self._active_series_tasks_lock = asyncio.Lock()
        self._active_series_ids: set[str] = set()
        self._active_series_run_ids: dict[str, str | None] = {}
        self._activity_lock = Lock()

    def is_video_generation_active(self, series_id: str, video_id: str) -> bool:
        return self._generator.is_video_generation_active(series_id, video_id)

    def is_series_generation_active(self, series_id: str) -> bool:
        with self._activity_lock:
            if series_id in self._active_series_ids:
                return True
        return self._generator.is_series_generation_active(series_id)

    def get_active_video_ids(self, series_id: str) -> list[str]:
        return self._generator.get_active_video_ids(series_id)

    def get_active_run_id(self, series_id: str) -> str | None:
        with self._activity_lock:
            return self._active_series_run_ids.get(series_id)

    async def run(
        self,
        series_id: str,
        *,
        transcript_enhancement_enabled: bool | None = None,
        run_id: str | None = None,
    ) -> SeriesGenerationResult:
        task_id = f"series/{series_id}"
        task = await self._get_or_create_series_task(
            task_id=task_id,
            series_id=series_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            run_id=run_id,
        )
        return await asyncio.shield(task)

    async def _get_or_create_series_task(
        self,
        *,
        task_id: str,
        series_id: str,
        transcript_enhancement_enabled: bool | None,
        run_id: str | None,
    ) -> asyncio.Task[SeriesGenerationResult]:
        async with self._active_series_tasks_lock:
            existing = self._active_series_tasks.get(task_id)
            if existing is not None and not existing.done():
                raise DuplicateSeriesGenerationError(f"series '{series_id}' generation is already running")

            task = asyncio.create_task(
                self._run_series_generation(
                    task_id=task_id,
                    series_id=series_id,
                    transcript_enhancement_enabled=transcript_enhancement_enabled,
                )
            )
            self._active_series_tasks[task_id] = task
            with self._activity_lock:
                self._active_series_ids.add(series_id)
                self._active_series_run_ids[series_id] = run_id
            return task

    async def _run_series_generation(
        self,
        *,
        task_id: str,
        series_id: str,
        transcript_enhancement_enabled: bool | None,
    ) -> SeriesGenerationResult:
        try:
            series = self._get_series(series_id)
            pending_videos = [video for video in series.videos if not video.processed]
            reporter = self._progress_tracker.create_reporter(task_id)

            if not pending_videos:
                reporter.completed("该系列下所有视频都已生成概况")
                return SeriesGenerationResult(
                    series_id=series_id,
                    completed_videos=[],
                    skipped_videos=[],
                    cancelled_videos=[],
                )

            completed_video_ids: set[str] = set()
            cancelled_video_ids: set[str] = set()
            failure: Exception | None = None
            cancellation_requested = asyncio.Event()
            results_lock = asyncio.Lock()
            queue: asyncio.Queue[tuple[int, object]] = asyncio.Queue()
            for index, video in enumerate(pending_videos, start=1):
                queue.put_nowait((index, video))

            worker_count = min(self._generator.generation_concurrency, len(pending_videos))

            async def update_series_progress() -> None:
                async with results_lock:
                    progress = (len(completed_video_ids) / len(pending_videos)) * 100.0
                    counts = (
                        f"已完成 {len(completed_video_ids)} / {len(pending_videos)}"
                        f"，完成 {len(completed_video_ids)}"
                        f"，取消 {len(cancelled_video_ids)}"
                    )
                    reporter.update("batch", progress, counts)

            async def worker() -> None:
                nonlocal failure
                while (
                    failure is None
                    and not reporter.is_cancel_requested()
                    and not cancellation_requested.is_set()
                ):
                    try:
                        _, video = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return

                    child_reporter = _SeriesVideoProgressReporter(
                        base_reporter=reporter,
                        video_reporter=self._progress_tracker.create_reporter(f"{series_id}/{video.id}"),
                        cancellation_requested=cancellation_requested,
                    )
                    try:
                        result = await self._generator.run(
                            series_id,
                            video.id,
                            transcript_enhancement_enabled=transcript_enhancement_enabled,
                            progress_reporter=child_reporter,
                        )
                        if result is None:
                            if failure is not None:
                                return
                            async with results_lock:
                                cancelled_video_ids.add(video.id)
                            await update_series_progress()
                            continue
                        async with results_lock:
                            completed_video_ids.add(video.id)
                        await update_series_progress()
                    except Exception as error:
                        failure = error
                        cancellation_requested.set()
                        return
                    finally:
                        queue.task_done()

            workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
            try:
                await asyncio.gather(*workers)
            finally:
                for worker_task in workers:
                    if not worker_task.done():
                        worker_task.cancel()

            if failure is not None:
                raise failure

            completed_videos = [video.id for video in pending_videos if video.id in completed_video_ids]
            cancelled_videos = [video.id for video in pending_videos if video.id in cancelled_video_ids]
            skipped_videos = [
                video.id
                for video in pending_videos
                if video.id not in completed_video_ids and video.id not in cancelled_video_ids
            ]
            if reporter.is_cancel_requested():
                reporter.cancelled(
                    f"系列处理已取消，已结束 {len(completed_videos) + len(cancelled_videos)} / {len(pending_videos)}"
                    f"，完成 {len(completed_videos)}，取消 {len(cancelled_videos)}"
                )
                return SeriesGenerationResult(
                    series_id=series_id,
                    completed_videos=completed_videos,
                    skipped_videos=skipped_videos,
                    cancelled_videos=cancelled_videos,
                    cancelled_video_id=cancelled_videos[0] if cancelled_videos else None,
                )

            reporter.completed(
                f"系列处理完成，已结束 {len(completed_videos) + len(cancelled_videos)} / {len(pending_videos)}"
                f"，完成 {len(completed_videos)}，取消 {len(cancelled_videos)}"
            )
            return SeriesGenerationResult(
                series_id=series_id,
                completed_videos=completed_videos,
                skipped_videos=[],
                cancelled_videos=cancelled_videos,
                cancelled_video_id=cancelled_videos[0] if cancelled_videos else None,
            )
        finally:
            await self._clear_series_task(task_id)

    async def _clear_series_task(self, task_id: str) -> None:
        async with self._active_series_tasks_lock:
            current = self._active_series_tasks.get(task_id)
            if current is asyncio.current_task():
                self._active_series_tasks.pop(task_id, None)
                series_id = task_id.removeprefix("series/")
                with self._activity_lock:
                    self._active_series_ids.discard(series_id)
                    self._active_series_run_ids.pop(series_id, None)

    def _get_series(self, series_id: str) -> LibrarySeriesDTO:
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise LookupError(f"series not found '{series_id}'")
        return series


class _SeriesVideoProgressReporter:
    def __init__(
        self,
        *,
        base_reporter: ProgressReporter,
        video_reporter: ProgressReporter,
        cancellation_requested: asyncio.Event,
    ) -> None:
        self._base_reporter = base_reporter
        self._video_reporter = video_reporter
        self._cancellation_requested = cancellation_requested

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        self._video_reporter.update(stage, progress, detail)

    def completed(self, detail: str | None = None) -> None:
        self._video_reporter.completed(detail)

    def failed(self, message: str) -> None:
        self._video_reporter.failed(message)
        self._base_reporter.failed(message)

    def cancelled(self, detail: str | None = None) -> None:
        self._video_reporter.cancelled(detail)

    def is_cancel_requested(self) -> bool:
        return (
            self._cancellation_requested.is_set()
            or self._base_reporter.is_cancel_requested()
            or self._video_reporter.is_cancel_requested()
        )

    def raise_if_cancelled(self) -> None:
        if self._cancellation_requested.is_set():
            raise GenerateCancelledError("系列处理已停止")
        try:
            self._video_reporter.raise_if_cancelled()
            self._base_reporter.raise_if_cancelled()
        except RuntimeError as error:
            raise GenerateCancelledError(str(error) or "任务已取消") from error
