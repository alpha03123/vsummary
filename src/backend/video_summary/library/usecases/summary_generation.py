from __future__ import annotations

import asyncio

from backend.video_summary.library.models import VideoSummaryDTO
from backend.video_summary.library.ports import (
    VideoGenerationProgressTracker,
    VideoLibraryReader,
    VideoSummaryGenerator,
)


class GenerateVideoSummaryFromLibrary:
    def __init__(
        self,
        workspace: VideoLibraryReader,
        generator: VideoSummaryGenerator,
        progress_tracker: VideoGenerationProgressTracker,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._progress_tracker = progress_tracker
        self._active_tasks: dict[str, asyncio.Task[VideoSummaryDTO | None]] = {}
        self._active_tasks_lock = asyncio.Lock()
        self._generation_slot = asyncio.Semaphore(1)

    async def run(
        self,
        series_id: str,
        video_id: str,
        transcript_enhancement_enabled: bool | None = None,
    ) -> VideoSummaryDTO | None:
        task_id = f"{series_id}/{video_id}"
        task = await self._get_or_create_task(
            task_id=task_id,
            series_id=series_id,
            video_id=video_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
        )
        return await asyncio.shield(task)

    async def _get_or_create_task(
        self,
        *,
        task_id: str,
        series_id: str,
        video_id: str,
        transcript_enhancement_enabled: bool | None,
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
    ) -> VideoSummaryDTO | None:
        reporter = self._progress_tracker.create_reporter(f"{series_id}/{video_id}")
        try:
            if self._generation_slot.locked():
                reporter.update("prepare", 0.0, "正在等待当前生成任务完成")

            async with self._generation_slot:
                await self._generator.run(
                    series_id=series_id,
                    video_id=video_id,
                    progress_reporter=reporter,
                    transcript_enhancement_enabled=transcript_enhancement_enabled,
                )
            reporter.completed("AI 概况已生成")
            return self._workspace.get_video_summary(series_id, video_id)
        except LookupError:
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
