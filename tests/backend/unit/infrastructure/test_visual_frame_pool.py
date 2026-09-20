from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path

from PIL import Image

from backend.video_summary.infrastructure.visual_frame_pool import build_or_load_visual_frame_pool


class FakeFrameProcessor:
    def __init__(self, duration: float) -> None:
        self.duration = duration
        self.calls: list[float] = []

    def probe_duration(self, video_path: Path) -> float:
        return self.duration

    def extract_frame(self, video_path: Path, timestamp_seconds: float, output_path: Path) -> Path:
        self.calls.append(timestamp_seconds)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 36), color=(int(timestamp_seconds * 10) % 255, 20, 30)).save(output_path)
        return output_path


class VisualFramePoolTests(unittest.TestCase):
    def test_caps_grid_images_and_reuses_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processor = FakeFrameProcessor(duration=180)
            first = build_or_load_visual_frame_pool(
                video_path=root / "video.mp4",
                output_dir=root / "output",
                max_input_images=2,
                media_processor=processor,
            )
            calls_after_first = list(processor.calls)
            second = build_or_load_visual_frame_pool(
                video_path=root / "video.mp4",
                output_dir=root / "output",
                max_input_images=2,
                media_processor=processor,
            )

            self.assertEqual(2, len(first.image_paths))
            self.assertEqual(18, len(calls_after_first))
            self.assertEqual(calls_after_first, processor.calls)
            self.assertEqual(first.image_paths, second.image_paths)
            self.assertFalse((root / "output" / "visual_frame_pool" / "grid-2" / "raw").exists())

    def test_keeps_incomplete_tail_grid_for_short_videos(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool = build_or_load_visual_frame_pool(
                video_path=root / "video.mp4",
                output_dir=root / "output",
                max_input_images=10,
                media_processor=FakeFrameProcessor(duration=20),
            )

            self.assertEqual(3, len(pool.image_paths))
            self.assertEqual(2, len(pool.timestamps_by_image[-1]))
            self.assertFalse((root / "output" / "visual_frame_pool" / "grid-10" / "raw").exists())

    def test_serializes_concurrent_builds_for_the_same_pool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processor = FakeFrameProcessor(duration=20)

            def build_pool():
                return build_or_load_visual_frame_pool(
                    video_path=root / "video.mp4",
                    output_dir=root / "output",
                    max_input_images=2,
                    media_processor=processor,
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                first, second = list(executor.map(lambda _item: build_pool(), range(2)))

            self.assertEqual(first.image_paths, second.image_paths)
            self.assertTrue(all(path.is_file() for path in first.image_paths))
            self.assertFalse((root / "output" / "visual_frame_pool" / "grid-2" / "raw").exists())


if __name__ == "__main__":
    unittest.main()
