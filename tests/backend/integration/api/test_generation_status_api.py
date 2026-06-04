from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


from backend.api.app import create_app
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.library.usecases.summary_generation import DuplicateSeriesGenerationError


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
    return SimpleNamespace(
        root_dir=None,
        generation_progress_tracker=tracker,
        get_video_source=source_runner,
        generate_series_summaries=SimpleNamespace(run=lambda series_id, transcript_enhancement_enabled=None: None),
    )


async def _raise_duplicate_series(series_id: str, transcript_enhancement_enabled=None):
    del transcript_enhancement_enabled
    raise DuplicateSeriesGenerationError(f"series '{series_id}' generation is already running")


def _complete_reporter_after_delay(reporter) -> None:
    time.sleep(0.1)
    reporter.completed("done")


if __name__ == "__main__":
    unittest.main()
