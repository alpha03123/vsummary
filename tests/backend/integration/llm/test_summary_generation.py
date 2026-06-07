from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.library.models import (
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoSummaryDTO,
    WorkspaceDTO,
)
from backend.video_summary.library.usecases.summary_generation import (
    GenerationScopeBusyError,
    GenerateSeriesSummaryFromLibrary,
    GenerateVideoSummaryFromLibrary,
)


class SummaryGenerationCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_video_requests_reuse_one_underlying_generator_call(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace()
        generator = BlockingGenerator()
        use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=2,
        )

        first_task = asyncio.create_task(use_case.run("series-1", "video-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)
        second_task = asyncio.create_task(use_case.run("series-1", "video-1"))
        await asyncio.sleep(0)
        generator.release.set()

        await asyncio.gather(first_task, second_task)

        self.assertEqual(generator.calls, [("series-1", "video-1")])

    async def test_single_video_reports_generation_active_until_task_finishes(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace()
        generator = BlockingGenerator()
        use_case = GenerateVideoSummaryFromLibrary(workspace, generator, tracker)

        task = asyncio.create_task(use_case.run("series-1", "video-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)

        self.assertTrue(use_case.is_video_generation_active("series-1", "video-1"))
        self.assertTrue(use_case.is_series_generation_active("series-1"))

        generator.release.set()
        await task

        self.assertFalse(use_case.is_video_generation_active("series-1", "video-1"))
        self.assertFalse(use_case.is_series_generation_active("series-1"))

    async def test_two_different_videos_can_run_concurrently_when_video_generation_concurrency_is_two(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = BlockingGenerator()
        use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=2,
        )

        task_one = asyncio.create_task(use_case.run("series-1", "video-1"))
        task_two = asyncio.create_task(use_case.run("series-1", "video-2"))
        await asyncio.wait_for(generator.started_two.wait(), timeout=1.0)
        self.assertEqual(generator.max_active, 2)
        generator.release.set()

        await asyncio.gather(task_one, task_two)

    async def test_third_video_waits_when_video_generation_concurrency_is_two(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = BlockingGenerator()
        use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=2,
        )

        task_one = asyncio.create_task(use_case.run("series-1", "video-1"))
        task_two = asyncio.create_task(use_case.run("series-1", "video-2"))
        await asyncio.wait_for(generator.started_two.wait(), timeout=1.0)
        task_three = asyncio.create_task(use_case.run("series-1", "video-3"))

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(generator.third_started.wait(), timeout=0.1)

        generator.release_one()
        await asyncio.wait_for(generator.third_started.wait(), timeout=1.0)
        generator.release.set()

        await asyncio.gather(task_one, task_two, task_three)

    async def test_single_video_cancel_marks_reporter_cancelled(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace()
        generator = CancelledGenerator()
        use_case = GenerateVideoSummaryFromLibrary(workspace, generator, tracker)

        result = await use_case.run("series-1", "video-1")

        self.assertIsNone(result)
        reporter = tracker.reporters["series-1/video-1"]
        self.assertEqual(reporter.cancelled_calls, ["AI 概况生成已取消"])
        self.assertEqual(reporter.failed_calls, [])

    async def test_series_batch_single_video_cancel_continues_with_remaining_videos(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = BatchAwareGenerator(
            outcomes={
                ("series-1", "video-1"): "completed",
                ("series-1", "video-2"): "cancelled",
                ("series-1", "video-3"): "completed",
            }
        )
        single_use_case = GenerateVideoSummaryFromLibrary(workspace, generator, tracker)
        batch_use_case = GenerateSeriesSummaryFromLibrary(workspace, single_use_case, tracker)

        summary = await batch_use_case.run("series-1")

        self.assertEqual(summary.completed_videos, ["video-1", "video-3"])
        self.assertEqual(summary.cancelled_videos, ["video-2"])
        self.assertEqual(summary.skipped_videos, [])
        self.assertEqual(generator.calls, [("series-1", "video-1"), ("series-1", "video-2"), ("series-1", "video-3")])
        reporter = tracker.reporters["series/series-1"]
        self.assertEqual(reporter.completed_calls, ["系列处理完成，已结束 3 / 3，完成 2，取消 1"])

    async def test_series_batch_keeps_child_stage_progress_on_video_task(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = StageReportingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(workspace, generator, tracker)
        batch_use_case = GenerateSeriesSummaryFromLibrary(workspace, single_use_case, tracker)

        await batch_use_case.run("series-1")

        reporter = tracker.reporters["series-1/video-1"]
        stage_names = [stage for stage, _, _ in reporter.updates]
        self.assertIn("probe", stage_names)
        self.assertIn("transcribe", stage_names)
        series_reporter = tracker.reporters["series/series-1"]
        self.assertFalse(any(detail and "正在处理 1/1：Video 1" in detail for _, _, detail in series_reporter.updates))

    async def test_series_batch_reuses_single_video_concurrency_limit(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = BlockingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=3,
        )
        batch_use_case = GenerateSeriesSummaryFromLibrary(
            workspace,
            single_use_case,
            tracker,
        )

        task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.third_started.wait(), timeout=1.0)
        self.assertEqual(generator.max_active, 3)
        generator.release.set()
        result = await task

        self.assertEqual(result.completed_videos, ["video-1", "video-2", "video-3"])

    async def test_series_batch_preserves_original_video_order_when_finishes_out_of_order(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = OutOfOrderCompletionGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=3,
        )
        batch_use_case = GenerateSeriesSummaryFromLibrary(
            workspace,
            single_use_case,
            tracker,
        )

        result = await batch_use_case.run("series-1")

        self.assertEqual(generator.max_active, 3)
        self.assertEqual(result.completed_videos, ["video-1", "video-2", "video-3"])

    async def test_duplicate_series_batch_request_is_rejected_while_same_series_is_running(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = BlockingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=1,
        )
        batch_use_case = GenerateSeriesSummaryFromLibrary(
            workspace,
            single_use_case,
            tracker,
        )

        first_task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)

        with self.assertRaisesRegex(RuntimeError, "series-1"):
            await batch_use_case.run("series-1")

        generator.release.set()
        await first_task

    async def test_single_video_request_is_rejected_while_series_batch_is_running(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                    ],
                ),
                LibrarySeriesDTO(
                    id="series-2",
                    title="Series 2",
                    videos=[
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                ),
            ]
        )
        generator = BlockingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(workspace, generator, tracker)
        batch_use_case = GenerateSeriesSummaryFromLibrary(workspace, single_use_case, tracker)

        task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)

        with self.assertRaisesRegex(GenerationScopeBusyError, "series generation"):
            await single_use_case.run("series-2", "video-3")

        generator.release.set()
        await task

    async def test_series_batch_request_is_rejected_while_single_video_is_running(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                    ],
                ),
                LibrarySeriesDTO(
                    id="series-2",
                    title="Series 2",
                    videos=[
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                ),
            ]
        )
        generator = BlockingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(workspace, generator, tracker)
        batch_use_case = GenerateSeriesSummaryFromLibrary(workspace, single_use_case, tracker)

        task = asyncio.create_task(single_use_case.run("series-1", "video-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)

        with self.assertRaisesRegex(GenerationScopeBusyError, "video generation"):
            await batch_use_case.run("series-2")

        generator.release.set()
        await task

    async def test_series_batch_reports_generation_active_until_task_finishes(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = BlockingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(workspace, generator, tracker)
        batch_use_case = GenerateSeriesSummaryFromLibrary(workspace, single_use_case, tracker)

        task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)

        self.assertTrue(batch_use_case.is_series_generation_active("series-1"))
        self.assertTrue(batch_use_case.is_video_generation_active("series-1", "video-1"))

        generator.release.set()
        await task

        self.assertFalse(batch_use_case.is_series_generation_active("series-1"))
        self.assertFalse(batch_use_case.is_video_generation_active("series-1", "video-1"))

    async def test_series_batch_single_video_cancel_does_not_skip_not_started_work(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = CoordinatedOutcomeGenerator(
            outcomes={
                "video-1": ("wait", None),
                "video-2": ("cancel", None),
                "video-3": ("complete", None),
            }
        )
        single_use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=3,
        )
        batch_use_case = GenerateSeriesSummaryFromLibrary(
            workspace,
            single_use_case,
            tracker,
        )

        task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.started_two.wait(), timeout=1.0)
        generator.release_waiting("video-1")
        result = await task

        self.assertEqual(result.completed_videos, ["video-1", "video-3"])
        self.assertEqual(result.cancelled_videos, ["video-2"])
        self.assertEqual(result.skipped_videos, [])
        self.assertEqual(generator.calls, ["video-1", "video-2", "video-3"])

    async def test_series_batch_cancel_skips_not_started_work(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = BlockingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=1,
        )
        batch_use_case = GenerateSeriesSummaryFromLibrary(workspace, single_use_case, tracker)

        task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)
        tracker.reporters["series/series-1"].cancel_requested = True
        generator.release.set()
        result = await task

        self.assertEqual(result.completed_videos, ["video-1"])
        self.assertEqual(result.cancelled_videos, [])
        self.assertEqual(result.skipped_videos, ["video-2", "video-3"])
        self.assertEqual(generator.calls, [("series-1", "video-1")])

    async def test_series_batch_cancel_marks_running_child_cancelled(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = ProgressCheckingGenerator()
        single_use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=1,
        )
        batch_use_case = GenerateSeriesSummaryFromLibrary(workspace, single_use_case, tracker)

        task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.started.wait(), timeout=1.0)
        tracker.reporters["series/series-1"].cancel_requested = True
        generator.release.set()
        result = await task

        self.assertEqual(result.completed_videos, [])
        self.assertEqual(result.cancelled_videos, ["video-1"])
        self.assertEqual(result.skipped_videos, ["video-2"])

    async def test_series_batch_failure_propagates_error(self) -> None:
        tracker = FakeProgressTracker()
        workspace = FakeWorkspace(
            series=[
                LibrarySeriesDTO(
                    id="series-1",
                    title="Series 1",
                    videos=[
                        LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-2", title="Video 2", source_name="video-2.mp4", processed=False, status="pending"),
                        LibraryVideoCardDTO(id="video-3", title="Video 3", source_name="video-3.mp4", processed=False, status="pending"),
                    ],
                )
            ]
        )
        generator = CoordinatedOutcomeGenerator(
            outcomes={
                "video-1": ("fail", RuntimeError("video-1 failed")),
                "video-2": ("wait", None),
                "video-3": ("complete", None),
            }
        )
        single_use_case = GenerateVideoSummaryFromLibrary(
            workspace,
            generator,
            tracker,
            video_generation_concurrency=3,
        )
        batch_use_case = GenerateSeriesSummaryFromLibrary(
            workspace,
            single_use_case,
            tracker,
        )

        task = asyncio.create_task(batch_use_case.run("series-1"))
        await asyncio.wait_for(generator.started_two.wait(), timeout=1.0)
        generator.release_waiting("video-2")
        with self.assertRaisesRegex(RuntimeError, "video-1 failed"):
            await task

        self.assertIn("video-1", generator.calls)


class FakeWorkspace:
    def __init__(self, series: list[LibrarySeriesDTO] | None = None) -> None:
        self._workspace = WorkspaceDTO(id="workspace", title="Workspace")
        self._series = series or [
            LibrarySeriesDTO(
                id="series-1",
                title="Series 1",
                videos=[LibraryVideoCardDTO(id="video-1", title="Video 1", source_name="video-1.mp4", processed=False, status="pending")],
            )
        ]

    def get_workspace(self) -> WorkspaceDTO:
        return self._workspace

    def list_series(self) -> list[LibrarySeriesDTO]:
        return self._series

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        return VideoSummaryDTO(series_id=series_id, video_id=video_id, title=video_id, summary={"title": video_id})


class FakeProgressTracker:
    def __init__(self) -> None:
        self.reporters: dict[str, FakeReporter] = {}

    def create_reporter(self, task_id: str) -> "FakeReporter":
        reporter = FakeReporter()
        self.reporters[task_id] = reporter
        return reporter


class FakeReporter:
    def __init__(self) -> None:
        self.updates: list[tuple[str, float | None, str | None]] = []
        self.completed_calls: list[str | None] = []
        self.failed_calls: list[str] = []
        self.cancelled_calls: list[str | None] = []
        self.cancel_requested = False

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        self.updates.append((stage, progress, detail))

    def completed(self, detail: str | None = None) -> None:
        self.completed_calls.append(detail)

    def failed(self, message: str) -> None:
        self.failed_calls.append(message)

    def cancelled(self, detail: str | None = None) -> None:
        self.cancelled_calls.append(detail)

    def is_cancel_requested(self) -> bool:
        return self.cancel_requested

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise RuntimeError("任务已取消")


class CancelledGenerator:
    async def run(self, *, series_id: str, video_id: str, progress_reporter=None, transcript_enhancement_enabled: bool | None = None) -> None:
        raise GenerateCancelledError("生成已取消")


class BatchAwareGenerator:
    def __init__(self, *, outcomes: dict[tuple[str, str], str]) -> None:
        self._outcomes = outcomes
        self.calls: list[tuple[str, str]] = []

    async def run(self, *, series_id: str, video_id: str, progress_reporter=None, transcript_enhancement_enabled: bool | None = None) -> None:
        key = (series_id, video_id)
        self.calls.append(key)
        outcome = self._outcomes.get(key, "completed")
        if outcome == "cancelled":
            raise GenerateCancelledError("生成已取消")


class StageReportingGenerator:
    async def run(self, *, series_id: str, video_id: str, progress_reporter=None, transcript_enhancement_enabled: bool | None = None) -> None:
        progress_reporter.update("probe", 5.0, "正在分析视频信息")
        progress_reporter.update("transcribe", 60.0, "Whisper 正在转写音频")


class BlockingGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.started = asyncio.Event()
        self.started_two = asyncio.Event()
        self.third_started = asyncio.Event()
        self.release = asyncio.Event()
        self._release_next: asyncio.Queue[None] = asyncio.Queue()

    async def run(self, *, series_id: str, video_id: str, progress_reporter=None, transcript_enhancement_enabled: bool | None = None) -> None:
        del progress_reporter, transcript_enhancement_enabled
        self.calls.append((series_id, video_id))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if len(self.calls) >= 1:
            self.started.set()
        if self.active >= 2:
            self.started_two.set()
        if len(self.calls) >= 3:
            self.third_started.set()
        try:
            release_next_task = asyncio.create_task(self._release_next.get())
            release_all_task = asyncio.create_task(self.release.wait())
            done, pending = await asyncio.wait(
                {release_next_task, release_all_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                await task
        finally:
            self.active -= 1

    def release_one(self) -> None:
        self._release_next.put_nowait(None)


class ProgressCheckingGenerator:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, *, series_id: str, video_id: str, progress_reporter=None, transcript_enhancement_enabled: bool | None = None) -> None:
        del series_id, video_id, transcript_enhancement_enabled
        self.started.set()
        await self.release.wait()
        progress_reporter.raise_if_cancelled()


class OutOfOrderCompletionGenerator:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self._delays = {
            "video-1": 0.06,
            "video-2": 0.03,
            "video-3": 0.01,
        }

    async def run(self, *, series_id: str, video_id: str, progress_reporter=None, transcript_enhancement_enabled: bool | None = None) -> None:
        del series_id, progress_reporter, transcript_enhancement_enabled
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self._delays[video_id])
        finally:
            self.active -= 1


class CoordinatedOutcomeGenerator:
    def __init__(self, *, outcomes: dict[str, tuple[str, Exception | None]]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []
        self.started_two = asyncio.Event()
        self._waiting: dict[str, asyncio.Event] = {}

    async def run(self, *, series_id: str, video_id: str, progress_reporter=None, transcript_enhancement_enabled: bool | None = None) -> None:
        del series_id, progress_reporter, transcript_enhancement_enabled
        self.calls.append(video_id)
        if len(self.calls) >= 2:
            self.started_two.set()
        outcome, error = self._outcomes[video_id]
        if outcome == "wait":
            gate = self._waiting.setdefault(video_id, asyncio.Event())
            await gate.wait()
            return
        if outcome == "cancel":
            raise GenerateCancelledError("生成已取消")
        if outcome == "fail":
            raise error or RuntimeError("failed")
        return

    def release_waiting(self, video_id: str) -> None:
        self._waiting.setdefault(video_id, asyncio.Event()).set()


if __name__ == "__main__":
    unittest.main()
