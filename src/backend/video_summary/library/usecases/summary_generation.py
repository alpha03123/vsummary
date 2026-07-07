"""视频与系列级总结的生成用例集合（编排层）。

本模块负责"在视频库这一层如何把生成任务跑起来"：
- `GenerateVideoSummaryFromLibrary` 包装单视频生成，提供并发限流、活跃任务
  追踪、SSE 进度接入与可选的"系列知识记忆"刷新钩子；
- `GenerateSeriesSummaryFromLibrary` 在前者的能力之上做系列级批量调度：
  维护任务队列、worker 协程、取消传播与最终结果归类。
两个用例被设计为可独立注入的 `use cases`，由 API 路由按需选用。
"""

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
    """系列级批量生成结束后的归类结果。

    Attributes:
        series_id: 目标系列 ID。
        completed_videos: 已成功生成总结的视频 ID 列表（顺序与系列一致）。
        skipped_videos: 因前置条件不满足而被跳过的视频 ID 列表。
        cancelled_videos: 用户取消时正在处理/已停止的视频 ID 列表。
        cancelled_video_id: 若发生整批取消，给出首个被取消的视频 ID 便于
            前端跳转展示；若为 `None` 表示本次未触发取消。
    """

    series_id: str
    completed_videos: list[str]
    skipped_videos: list[str]
    cancelled_videos: list[str]
    cancelled_video_id: str | None = None


class DuplicateSeriesGenerationError(RuntimeError):
    """对同一系列重复启动批量生成时抛出。"""


class GenerationScopeBusyError(RuntimeError):
    """在已有生成任务占用资源时启动新任务时抛出（例如系列生成进行中又触发单视频生成）。"""


class GenerateVideoSummaryFromLibrary:
    """单视频总结生成的"库层"用例。

    业务场景：用户在某个视频上点击"生成 AI 概况"，本用例被触发；它负责
    维护当前正在跑的任务集合、并发限流（基于 anyio `CapacityLimiter`），
    并把"生成完成 → 写回总结 → 触发系列知识记忆刷新"封装为可被并发调用的
    安全单元。系列级批量生成会复用本用例作为 worker 入口。
    """

    def __init__(
        self,
        workspace: VideoLibraryReader,
        generator: VideoSummaryGenerator,
        progress_tracker: VideoGenerationProgressTracker,
        video_generation_concurrency: int = 1,
        series_memory_refresher: SeriesKnowledgeMemoryRefresher | None = None,
    ) -> None:
        """注入工作区读取端口、生成器、进度跟踪器、并发上限与可选的系列记忆刷新器。

        Args:
            workspace: 用于在生成结束后回读最新的总结 DTO。
            generator: 真正驱动转写 + LLM 总结的下游端口。
            progress_tracker: 创建 SSE 进度 reporter 的工厂。
            video_generation_concurrency: 单视频级并发上限（默认 1）。
            series_memory_refresher: 单视频完成后用于刷新系列目录记忆的可选钩子；
                为 `None` 时跳过。
        """
        self._workspace = workspace
        self._generator = generator
        self._progress_tracker = progress_tracker
        self._series_memory_refresher = series_memory_refresher
        self._active_tasks: dict[str, asyncio.Task[VideoSummaryDTO | None]] = {}
        self._active_tasks_lock = asyncio.Lock()
        self._active_task_keys: set[tuple[str, str]] = set()
        self._active_series_generation_ids: set[str] = set()
        self._activity_lock = Lock()
        self._video_generation_slots = CapacityLimiter(max(1, video_generation_concurrency))

    def update_video_generation_concurrency(self, video_generation_concurrency: int) -> None:
        """动态调整单视频级并发上限；运行中的任务不受影响。"""
        self._video_generation_slots.total_tokens = max(1, video_generation_concurrency)

    @property
    def generation_concurrency(self) -> int:
        """当前配置的单视频级并发上限。"""
        return int(self._video_generation_slots.total_tokens)

    def is_video_generation_active(self, series_id: str, video_id: str) -> bool:
        """判断指定视频是否仍有进行中的生成任务。"""
        with self._activity_lock:
            return (series_id, video_id) in self._active_task_keys

    def is_series_generation_active(self, series_id: str) -> bool:
        """判断指定系列是否仍有进行中的生成任务（系列级或包含该系列的单视频）。"""
        with self._activity_lock:
            return (
                series_id in self._active_series_generation_ids
                or any(active_series_id == series_id for active_series_id, _ in self._active_task_keys)
            )

    def get_active_video_ids(self, series_id: str) -> list[str]:
        """返回指定系列下当前正在生成的视频 ID 列表（顺序无保证）。"""
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
        internal_series_generation: bool = False,
    ) -> VideoSummaryDTO | None:
        """为指定视频启动一次生成并返回最终总结 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            transcript_enhancement_enabled: 是否启用转写增强；为 `None` 时
                由生成器按默认配置决定。
            progress_reporter: 可选的自定义进度 reporter；为 `None` 时使用
                `progress_tracker` 创建的默认 reporter。
            internal_series_generation: 由系列批量生成内部调用时设为 `True`，
                跳过"系列批量进行中"的互斥检查。

        Returns:
            落盘后的 `VideoSummaryDTO`；视频不存在/被取消/总结缺失时返回 `None`，
            其余异常（生成失败、运行错误）会原样上抛。

        Raises:
            GenerationScopeBusyError: 已有系列批量生成在跑且 `internal_series_generation` 为 `False`。
        """
        task_id = f"{series_id}/{video_id}"
        task = await self._get_or_create_task(
            task_id=task_id,
            series_id=series_id,
            video_id=video_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            progress_reporter=progress_reporter,
            internal_series_generation=internal_series_generation,
        )
        return await asyncio.shield(task)

    def begin_series_generation(self, series_id: str) -> None:
        """声明一个系列即将进入批量生成，用于互斥检查。

        Args:
            series_id: 即将开始批量生成的系列 ID。

        Raises:
            GenerationScopeBusyError: 该系列已经在批量生成中，或全局存在其他
                进行中的单视频任务（确保批量期间不会被其他调用干扰）。
        """
        with self._activity_lock:
            if series_id in self._active_series_generation_ids:
                raise GenerationScopeBusyError(f"series '{series_id}' generation is already running")
            if self._active_task_keys:
                raise GenerationScopeBusyError("video generation is already running")
            self._active_series_generation_ids.add(series_id)

    def end_series_generation(self, series_id: str) -> None:
        """释放一个系列的批量生成占用标记。"""
        with self._activity_lock:
            self._active_series_generation_ids.discard(series_id)

    async def _get_or_create_task(
        self,
        *,
        task_id: str,
        series_id: str,
        video_id: str,
        transcript_enhancement_enabled: bool | None,
        progress_reporter: ProgressReporter | None,
        internal_series_generation: bool,
    ) -> asyncio.Task[VideoSummaryDTO | None]:
        """获取或创建单视频生成任务，复用已有任务避免重复触发。

        Returns:
            对应的 asyncio Task；调用方应通过 `asyncio.shield` 防止取消传播。

        Raises:
            GenerationScopeBusyError: 互斥条件不满足。
        """
        async with self._active_tasks_lock:
            with self._activity_lock:
                if not internal_series_generation and self._active_series_generation_ids:
                    raise GenerationScopeBusyError("series generation is already running")

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
        """执行单视频生成的实际步骤：占并发槽 → 调生成器 → 刷新系列记忆 → 回读 DTO。

        异常处理：
            - `LookupError` 视为"无制品"，返回 `None`；
            - `GenerateCancelledError` 视为用户取消，返回 `None`；
            - 其他 `RuntimeError` 与未知异常会先更新 reporter 失败状态再上抛。
        """
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
        """从活跃任务表中移除当前任务（仅在调用方就是当前 Task 时才生效）。"""
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
    """系列级批量总结生成的用例。

    业务场景：用户在工作区一次性触发"为整个系列生成 AI 概况"；本用例把
    系列下未处理的视频分发给 worker 协程并发跑（受 `generation_concurrency`
    限制），聚合结果并区分"完成/取消/失败"，通过 SSE 报告整体进度。

    实现要点：
    - 复用 `GenerateVideoSummaryFromLibrary` 作为单视频 worker；
    - 用 `asyncio.Queue` 调度待处理视频；
    - 通过 `_SeriesVideoProgressReporter` 把单视频进度透传到系列级 reporter；
    - 取消时取消所有 worker 协程并归类"已完成"和"已取消"集合。
    """

    def __init__(
        self,
        workspace: VideoLibraryReader,
        generator: GenerateVideoSummaryFromLibrary,
        progress_tracker: VideoGenerationProgressTracker,
    ) -> None:
        """注入只读端口、单视频生成器与进度跟踪器。"""
        self._workspace = workspace
        self._generator = generator
        self._progress_tracker = progress_tracker
        self._active_series_tasks: dict[str, asyncio.Task[SeriesGenerationResult]] = {}
        self._active_series_tasks_lock = asyncio.Lock()
        self._active_series_ids: set[str] = set()
        self._active_series_run_ids: dict[str, str | None] = {}
        self._activity_lock = Lock()

    def is_video_generation_active(self, series_id: str, video_id: str) -> bool:
        """委托给底层单视频生成器。"""
        return self._generator.is_video_generation_active(series_id, video_id)

    def is_series_generation_active(self, series_id: str) -> bool:
        """判断系列级或其中的单视频生成是否在跑。"""
        with self._activity_lock:
            if series_id in self._active_series_ids:
                return True
        return self._generator.is_series_generation_active(series_id)

    def get_active_video_ids(self, series_id: str) -> list[str]:
        """委托给底层单视频生成器。"""
        return self._generator.get_active_video_ids(series_id)

    def get_active_run_id(self, series_id: str) -> str | None:
        """返回指定系列当前正在跑的 run_id（用于前端区分多次重复触发）。"""
        with self._activity_lock:
            return self._active_series_run_ids.get(series_id)

    async def run(
        self,
        series_id: str,
        *,
        transcript_enhancement_enabled: bool | None = None,
        run_id: str | None = None,
    ) -> SeriesGenerationResult:
        """启动一次系列级批量生成并返回最终归类结果。

        Args:
            series_id: 目标系列 ID。
            transcript_enhancement_enabled: 是否启用转写增强；`None` 时由生成器决定。
            run_id: 外部传入的运行标识（用于在多次重复触发间做关联），
                为 `None` 时不强制要求匹配。

        Returns:
            包含完成/取消/跳过集合的 `SeriesGenerationResult`。

        Raises:
            DuplicateSeriesGenerationError: 该系列已有未完成的批量任务。
            LookupError: 系列不存在。
            Exception: 任意 worker 抛出的异常都会被包装为系列级失败上抛。
        """
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
        """获取或创建系列级生成任务；存在未完成任务时拒绝重复触发。"""
        async with self._active_series_tasks_lock:
            existing = self._active_series_tasks.get(task_id)
            if existing is not None and not existing.done():
                raise DuplicateSeriesGenerationError(f"series '{series_id}' generation is already running")
            self._generator.begin_series_generation(series_id)

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
        """实际执行系列级批量生成：调度 worker、收集结果、归类取消/完成。"""
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
                """把单视频完成/取消事件聚合成系列级进度并上报。"""
                async with results_lock:
                    progress = (len(completed_video_ids) / len(pending_videos)) * 100.0
                    counts = (
                        f"已完成 {len(completed_video_ids)} / {len(pending_videos)}"
                        f"，完成 {len(completed_video_ids)}"
                        f"，取消 {len(cancelled_video_ids)}"
                    )
                    reporter.update("batch", progress, counts)

            async def worker() -> None:
                """单 worker：从队列取视频并复用 `GenerateVideoSummaryFromLibrary` 跑生成。"""
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
                            internal_series_generation=True,
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
        """从活跃任务表中移除当前系列任务并释放占用标记。"""
        async with self._active_series_tasks_lock:
            current = self._active_series_tasks.get(task_id)
            if current is asyncio.current_task():
                self._active_series_tasks.pop(task_id, None)
                series_id = task_id.removeprefix("series/")
                with self._activity_lock:
                    self._active_series_ids.discard(series_id)
                    self._active_series_run_ids.pop(series_id, None)
                self._generator.end_series_generation(series_id)

    def _get_series(self, series_id: str) -> LibrarySeriesDTO:
        """从工作区读出系列 DTO；不存在则抛 `LookupError`。"""
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise LookupError(f"series not found '{series_id}'")
        return series


class _SeriesVideoProgressReporter:
    """系列批量生成场景下的复合进度 reporter。

    业务目的：让"系列级 reporter"和"单视频 reporter"看到的进度保持一致，
    并把"任意一层请求取消"和"任意一层失败"都向上传播；同时通过共享的
    `asyncio.Event` 让所有 worker 能在最快的情况下响应取消。
    """

    def __init__(
        self,
        *,
        base_reporter: ProgressReporter,
        video_reporter: ProgressReporter,
        cancellation_requested: asyncio.Event,
    ) -> None:
        """注入系列级 reporter、单视频 reporter 与共享的取消事件。"""
        self._base_reporter = base_reporter
        self._video_reporter = video_reporter
        self._cancellation_requested = cancellation_requested

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        """把进度更新转发给单视频 reporter。"""
        self._video_reporter.update(stage, progress, detail)

    def completed(self, detail: str | None = None) -> None:
        """单视频完成事件转发给单视频 reporter。"""
        self._video_reporter.completed(detail)

    def failed(self, message: str) -> None:
        """失败时同时通知单视频与系列级 reporter，确保两端都收到失败信号。"""
        self._video_reporter.failed(message)
        self._base_reporter.failed(message)

    def cancelled(self, detail: str | None = None) -> None:
        """单视频取消事件转发给单视频 reporter。"""
        self._video_reporter.cancelled(detail)

    def is_cancel_requested(self) -> bool:
        """任一来源请求取消时即视为取消。"""
        return (
            self._cancellation_requested.is_set()
            or self._base_reporter.is_cancel_requested()
            or self._video_reporter.is_cancel_requested()
        )

    def raise_if_cancelled(self) -> None:
        """若处于取消态，抛 `GenerateCancelledError` 让上层 worker 优雅退出。"""
        if self._cancellation_requested.is_set():
            raise GenerateCancelledError("系列处理已停止")
        try:
            self._video_reporter.raise_if_cancelled()
            self._base_reporter.raise_if_cancelled()
        except RuntimeError as error:
            raise GenerateCancelledError(str(error) or "任务已取消") from error
