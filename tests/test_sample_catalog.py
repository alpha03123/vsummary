from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.video_summary.infrastructure.sample_catalog import SampleSummaryCatalog


class SampleSummaryCatalogTests(unittest.TestCase):
    def test_list_videos_only_returns_directories_with_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "video_include"
            output_dir = root / "sample" / "output"
            kept_dir = output_dir / "ready-video"
            ignored_dir = output_dir / "empty-video"
            kept_dir.mkdir(parents=True)
            ignored_dir.mkdir(parents=True)
            (kept_dir / "summary.json").write_text(json.dumps({"title": "Ready"}), encoding="utf-8")

            catalog = SampleSummaryCatalog(root)

            videos = catalog.list_videos()

            self.assertEqual([video.id for video in videos], ["ready-video"])
            self.assertEqual(videos[0].title, "ready-video")

    def test_get_video_summary_uses_title_fallback_when_payload_title_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "video_include"
            summary_dir = root / "sample" / "output" / "video-1"
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text(
                json.dumps({"title": "   ", "chapters": []}),
                encoding="utf-8",
            )

            catalog = SampleSummaryCatalog(root)

            summary = catalog.get_video_summary("video-1")

            self.assertIsNotNone(summary)
            self.assertEqual(summary.title, "video-1")
            self.assertEqual(summary.summary["chapters"], [])


if __name__ == "__main__":
    unittest.main()
