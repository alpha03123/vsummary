from __future__ import annotations

import unittest

from backend.video_summary.adapters.progress.in_memory_progress_tracker import InMemoryProgressTracker


class GenerationProgressTrackerTests(unittest.TestCase):
    def test_get_snapshot_returns_idle_before_task_start(self) -> None:
        tracker = InMemoryProgressTracker()

        snapshot = tracker.get_snapshot("series-1/video-1")

        self.assertEqual(snapshot.status, "idle")
        self.assertIsNone(snapshot.stage)
        self.assertEqual(snapshot.sequence, 0)

    def test_request_cancel_marks_task_as_cancelling_until_reporter_finishes(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        reporter.update("summarize", 88.0, "正在生成 AI 概况")

        tracker.request_cancel("series-1/video-1")

        snapshot = tracker.get_snapshot("series-1/video-1")
        self.assertEqual(snapshot.status, "cancelling")
        self.assertEqual(snapshot.stage, "cancelling")
        self.assertTrue(tracker.is_cancel_requested("series-1/video-1"))

        reporter.cancelled("AI 概况生成已取消")
        self.assertEqual(tracker.get_snapshot("series-1/video-1").status, "cancelled")

    def test_reporter_update_preserves_cancelling_status_after_cancel_requested(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("model-download")
        reporter.update("download", 40.0, "正在下载模型")

        tracker.request_cancel("model-download")
        reporter.update("download", 41.0, "正在下载模型")

        snapshot = tracker.get_snapshot("model-download")
        self.assertEqual(snapshot.status, "cancelling")
        self.assertEqual(snapshot.stage, "cancelling")
        self.assertEqual(snapshot.progress, 40.0)

    def test_create_reporter_advances_sequence_after_idle_snapshot_was_read(self) -> None:
        tracker = InMemoryProgressTracker()

        idle = tracker.get_snapshot("model-download")
        reporter = tracker.create_reporter("model-download")
        running = tracker.get_snapshot("model-download")

        self.assertGreater(running.sequence, idle.sequence)
        self.assertEqual(running.status, "running")
        reporter.completed("done")


class TerminalStateProtectionTests(unittest.TestCase):
    def test_completed_write_is_dropped_when_status_is_cancelling(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        reporter.update("summarize", 88.0, "正在生成 AI 概况")
        tracker.request_cancel("series-1/video-1")

        reporter.completed("AI 概况已生成")

        snapshot = tracker.get_snapshot("series-1/video-1")
        self.assertEqual(snapshot.status, "cancelling")

    def test_completed_write_is_dropped_when_status_is_cancelled(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        tracker.request_cancel("series-1/video-1")
        reporter.cancelled("已取消")

        reporter.completed("AI 概况已生成")

        snapshot = tracker.get_snapshot("series-1/video-1")
        self.assertEqual(snapshot.status, "cancelled")

    def test_raise_if_cancelled_message_is_task_cancelled(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series-1/video-1")
        tracker.request_cancel("series-1/video-1")

        with self.assertRaisesRegex(RuntimeError, "任务已取消"):
            reporter.raise_if_cancelled()


if __name__ == "__main__":
    unittest.main()
