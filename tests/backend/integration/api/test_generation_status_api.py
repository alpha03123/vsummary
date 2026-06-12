from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


from backend.api.app import create_app
from backend.video_summary.summary_generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.adapters.progress.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.workspace.models import LibrarySeriesDTO, LibraryVideoCardDTO
from backend.video_summary.workspace.usecases.summary_generation import DuplicateSeriesGenerationError


class GenerationStatusApiTests(unittest.TestCase):
    def test_video_generation_status_returns_idle_before_task_start(self) -> None:
        tracker = InMemoryProgressTracker()
        client = TestClient(create_app(_build_container(tracker)))

        response = client.get("/api/videos/series-1/video-1/generate/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_id"], "series-1/video-1")
        self.assertEqual(payload["snapshot"]["status"], "idle")

    def test_video_generation_status_returns_running_snapshot(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        reporter.update("summarize", 88.0, "正在生成 AI 概况")
        client = TestClient(create_app(_build_container(tracker)))

        response = client.get("/api/videos/series-1/video-1/generate/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["snapshot"]["status"], "running")
        self.assertEqual(payload["snapshot"]["stage"], "summarize")
        self.assertEqual(payload["snapshot"]["progress"], 88.0)

    def test_video_generation_status_does_not_require_existing_video_source(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        reporter.cancelled("任务已取消")
        container = _build_container(tracker)
        container.get_video_source = SimpleNamespace(run=lambda series_id, video_id: None)
        client = TestClient(create_app(container))

        response = client.get("/api/videos/series-1/video-1/generate/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_id"], "series-1/video-1")
        self.assertEqual(payload["snapshot"]["status"], "cancelled")

    def test_series_generation_status_returns_running_snapshot(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series/series-1")
        reporter.update("batch", 40.0, "正在处理 2/5：Video 2")
        client = TestClient(create_app(_build_container(tracker)))

        response = client.get("/api/series/series-1/generate/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_id"], "series/series-1")
        self.assertEqual(payload["snapshot"]["status"], "running")
        self.assertEqual(payload["snapshot"]["stage"], "batch")
        self.assertEqual(payload["snapshot"]["progress"], 40.0)

    def test_duplicate_series_generate_request_returns_conflict(self) -> None:
        tracker = InMemoryProgressTracker()
        container = _build_container(tracker)
        container.generate_series_summaries = SimpleNamespace(
            run=_raise_duplicate_series,
        )
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate")

        self.assertEqual(response.status_code, 409)

    def test_series_cancel_marks_series_and_active_video_tasks(self) -> None:
        tracker = InMemoryProgressTracker()
        container = _build_container(tracker)
        container.generate_series_summaries = SimpleNamespace(
            get_active_video_ids=lambda series_id: ["video-1", "video-2"] if series_id == "series-1" else [],
        )
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(tracker.is_cancel_requested("series/series-1"))
        self.assertTrue(tracker.is_cancel_requested("series-1/video-1"))
        self.assertTrue(tracker.is_cancel_requested("series-1/video-2"))

    def test_stale_series_cancel_run_id_does_not_cancel_current_series_task(self) -> None:
        tracker = InMemoryProgressTracker()
        tracker.create_reporter("series/series-1").update("batch", 10.0, "new run")
        container = _build_container(tracker)
        container.generate_series_summaries = SimpleNamespace(
            get_active_video_ids=lambda series_id: ["video-1"] if series_id == "series-1" else [],
            get_active_run_id=lambda series_id: "new-run" if series_id == "series-1" else None,
        )
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate/cancel", json={"run_id": "old-run"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "stale")
        self.assertFalse(tracker.is_cancel_requested("series/series-1"))
        self.assertFalse(tracker.is_cancel_requested("series-1/video-1"))
        self.assertEqual(tracker.get_snapshot("series/series-1").status, "running")

    def test_video_generate_returns_conflict_when_generation_is_cancelled(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        reporter.cancelled("任务已取消")
        container = _build_container(tracker)

        async def _cancelled_generate(series_id: str, video_id: str, transcript_enhancement_enabled=None):
            del series_id, video_id, transcript_enhancement_enabled
            raise GenerateCancelledError("任务已取消")

        container.generate_video_summary = SimpleNamespace(run=_cancelled_generate)
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/video-1/generate")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "generation cancelled")

    def test_sse_progress_stream_emits_current_snapshot_immediately(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        reporter.update("summarize", 55.0, "正在生成 AI 概况")
        client = TestClient(create_app(_build_container(tracker)))
        finisher = threading.Thread(target=_complete_reporter_after_delay, args=(reporter,), daemon=True)
        finisher.start()

        with client.stream("GET", "/api/videos/series-1/video-1/generate/progress") as response:
            chunks = list(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn('"progress": 55.0', chunks[0])


def _build_container(tracker: InMemoryProgressTracker):
    source_runner = SimpleNamespace(run=lambda series_id, video_id: object())
    library = SimpleNamespace(
        series=[
            LibrarySeriesDTO(
                id="series-1",
                title="Series 1",
                videos=[
                    LibraryVideoCardDTO(
                        id="video-1",
                        title="Video 1",
                        source_name="video-1.mp4",
                        processed=False,
                        status="pending",
                    ),
                    LibraryVideoCardDTO(
                        id="video-2",
                        title="Video 2",
                        source_name="video-2.mp4",
                        processed=False,
                        status="pending",
                    ),
                ],
            ),
        ],
    )
    return SimpleNamespace(
        root_dir=None,
        generation_progress_tracker=tracker,
        video_download_progress_tracker=InMemoryProgressTracker(),
        list_video_library=SimpleNamespace(run=lambda: library),
        get_video_source=source_runner,
        generate_video_summary=SimpleNamespace(run=lambda series_id, video_id, transcript_enhancement_enabled=None: None),
        generate_series_summaries=SimpleNamespace(run=lambda series_id, transcript_enhancement_enabled=None: None),
    )


async def _raise_duplicate_series(series_id: str, transcript_enhancement_enabled=None, run_id=None):
    del transcript_enhancement_enabled, run_id
    raise DuplicateSeriesGenerationError(f"series '{series_id}' generation is already running")


def _complete_reporter_after_delay(reporter) -> None:
    time.sleep(0.1)
    reporter.completed("done")


if __name__ == "__main__":
    unittest.main()
