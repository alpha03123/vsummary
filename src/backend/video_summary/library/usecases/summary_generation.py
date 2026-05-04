from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

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
        self._video_generation_slots = CapacityLimiter(max(1, video_generation_concurrency))

    def update_video_generation_concurrency(self, video_generation_concurrency: int) -> None:
        self._video_generation_slots.total_tokens = max(1, video_generation_concurrency)

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
        owns_reporter = progress_reporter is None
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
            if owns_reporter:
                reporter.completed("AI 概况已生成")
            return self._workspace.get_video_summary(series_id, video_id)
        except LookupError:
            return None
        except GenerateCancelledError:
            if owns_reporter:
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


class GenerateSeriesSummaryFromLibrary:
    def __init__(
        self,
        workspace: VideoLibraryReader,
        generator: GenerateVideoSummaryFromLibrary,
        progress_tracker: VideoGenerationProgressTracker,
        video_generation_concurrency: int = 1,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._progress_tracker = progress_tracker
        self._video_generation_concurrency = max(1, video_generation_concurrency)
        self._active_series_tasks: dict[str, asyncio.Task[SeriesGenerationResult]] = {}
        self._active_series_tasks_lock = asyncio.Lock()

    def update_video_generation_concurrency(self, video_generation_concurrency: int) -> None:
        self._video_generation_concurrency = max(1, video_generation_concurrency)

    async def run(
        self,
        series_id: str,
        *,
        transcript_enhancement_enabled: bool | None = None,
    ) -> SeriesGenerationResult:
        task_id = f"series/{series_id}"
        task = await self._get_or_create_series_task(
            task_id=task_id,
            series_id=series_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
        )
        return await asyncio.shield(task)

    async def _get_or_create_series_task(
        self,
        *,
        task_id: str,
        series_id: str,
        transcript_enhancement_enabled: bool | None,
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
                return SeriesGenerationResult(series_id=series_id, completed_videos=[], skipped_videos=[])

            results: dict[str, str] = {}
            cancelled_video_id: str | None = None
            failure: Exception | None = None
            cancellation_requested = asyncio.Event()
            queue: asyncio.Queue[tuple[int, object]] = asyncio.Queue()
            for index, video in enumerate(pending_videos, start=1):
                queue.put_nowait((index, video))

            worker_count = min(self._video_generation_concurrency, len(pending_videos))

            async def worker() -> None:
                nonlocal cancelled_video_id, failure
                while (
                    failure is None
                    and not reporter.is_cancel_requested()
                    and not cancellation_requested.is_set()
                ):
                    try:
                        current_index, video = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return

                    reporter.update(
                        "prepare",
                        ((current_index - 1) / len(pending_videos)) * 100.0,
                        f"正在处理 {current_index}/{len(pending_videos)}：{video.title}",
                    )
                    child_reporter = _SeriesVideoProgressReporter(
                        base_reporter=reporter,
                        current_index=current_index,
                        total_videos=len(pending_videos),
                        current_title=video.title,
                    )
                    try:
                        result = await self._generator.run(
                            series_id,
                            video.id,
                            transcript_enhancement_enabled=transcript_enhancement_enabled,
                            progress_reporter=child_reporter,
                        )
                        if result is None:
                            cancelled_video_id = cancelled_video_id or video.id
                            results[video.id] = "cancelled"
                            cancellation_requested.set()
                            return
                        results[video.id] = "completed"
                    except Exception as error:
                        failure = error
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

            completed_videos = [video.id for video in pending_videos if results.get(video.id) == "completed"]
            skipped_videos = [
                video.id
                for video in pending_videos
                if results.get(video.id) != "completed" and video.id != cancelled_video_id
            ]
            if cancelled_video_id is not None or reporter.is_cancel_requested():
                reporter.cancelled(
                    f"批量处理已取消，已完成 {len(completed_videos)} / {len(pending_videos)} 个视频"
                )
                return SeriesGenerationResult(
                    series_id=series_id,
                    completed_videos=completed_videos,
                    skipped_videos=skipped_videos,
                    cancelled_video_id=cancelled_video_id,
                )

            reporter.completed(f"批量处理完成，已生成 {len(completed_videos)} 个视频")
            return SeriesGenerationResult(series_id=series_id, completed_videos=completed_videos, skipped_videos=[])
        finally:
            await self._clear_series_task(task_id)

    async def _clear_series_task(self, task_id: str) -> None:
        async with self._active_series_tasks_lock:
            current = self._active_series_tasks.get(task_id)
            if current is asyncio.current_task():
                self._active_series_tasks.pop(task_id, None)

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
        current_index: int,
        total_videos: int,
        current_title: str,
    ) -> None:
        self._base_reporter = base_reporter
        self._current_index = current_index
        self._total_videos = max(1, total_videos)
        self._current_title = current_title

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        if progress is None:
            overall_progress = ((self._current_index - 1) / self._total_videos) * 100.0
        else:
            bounded = max(0.0, min(100.0, progress))
            overall_progress = ((self._current_index - 1) + (bounded / 100.0)) / self._total_videos * 100.0

        detail_prefix = f"正在处理 {self._current_index}/{self._total_videos}：{self._current_title}"
        merged_detail = detail_prefix if not detail else f"{detail_prefix} · {detail}"
        self._base_reporter.update(stage, overall_progress, merged_detail)

    def completed(self, detail: str | None = None) -> None:
        return None

    def failed(self, message: str) -> None:
        self._base_reporter.failed(message)

    def cancelled(self, detail: str | None = None) -> None:
        self._base_reporter.cancelled(detail)

    def is_cancel_requested(self) -> bool:
        return self._base_reporter.is_cancel_requested()

    def raise_if_cancelled(self) -> None:
        self._base_reporter.raise_if_cancelled()
