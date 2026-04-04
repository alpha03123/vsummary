from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


class ProgressTrackerTests(unittest.TestCase):
    def test_progress_snapshot_exposes_elapsed_and_estimates(self) -> None:
        tracker = InMemoryProgressTracker()
        reporter = tracker.create_reporter("series/video")

        time.sleep(0.02)
        reporter.update("extract_audio", 20.0, "正在将视频转换为音频")
        first_snapshot = tracker.get_snapshot("series/video")

        self.assertEqual(first_snapshot.stage, "extract_audio")
        self.assertIsNotNone(first_snapshot.started_at)
        self.assertIsNotNone(first_snapshot.stage_started_at)
        self.assertGreater(first_snapshot.elapsed_seconds, 0.0)
        self.assertGreaterEqual(first_snapshot.stage_elapsed_seconds, 0.0)
        self.assertIsNotNone(first_snapshot.estimated_total_seconds)
        self.assertIsNotNone(first_snapshot.remaining_seconds)
        self.assertGreater(first_snapshot.remaining_seconds, 0.0)

        first_stage_started_at = first_snapshot.stage_started_at

        time.sleep(0.02)
        reporter.update("extract_audio", 35.0, "仍在提取音频")
        same_stage_snapshot = tracker.get_snapshot("series/video")
        self.assertEqual(same_stage_snapshot.stage_started_at, first_stage_started_at)

        time.sleep(0.02)
        reporter.update("transcribe", 60.0, "Whisper 正在转写音频")
        next_stage_snapshot = tracker.get_snapshot("series/video")
        self.assertEqual(next_stage_snapshot.stage, "transcribe")
        self.assertGreater(next_stage_snapshot.stage_started_at, first_stage_started_at)

        reporter.completed("已完成")
        completed_snapshot = tracker.get_snapshot("series/video")
        self.assertEqual(completed_snapshot.status, "completed")
        self.assertEqual(completed_snapshot.remaining_seconds, 0.0)
        self.assertAlmostEqual(
            completed_snapshot.estimated_total_seconds,
            completed_snapshot.elapsed_seconds,
            places=3,
        )


if __name__ == "__main__":
    unittest.main()
