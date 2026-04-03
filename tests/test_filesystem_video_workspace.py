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

from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace


class FileSystemVideoWorkspaceTests(unittest.TestCase):
    def test_list_series_groups_videos_and_marks_processed_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "video_include"
            (root / "videos" / "course-a").mkdir(parents=True)
            (root / "videos" / "course-b").mkdir(parents=True)
            (root / "videos" / "course-a" / "a1.mp4").write_text("video", encoding="utf-8")
            (root / "videos" / "course-a" / "a2.mp4").write_text("video", encoding="utf-8")
            (root / "videos" / "course-b" / "b1.mov").write_text("video", encoding="utf-8")
            (root / "workspace" / "course-a" / "a2").mkdir(parents=True)
            (root / "workspace" / "course-a" / "a2" / "summary.json").write_text(
                json.dumps({"title": "A2"}),
                encoding="utf-8",
            )

            workspace = FileSystemVideoWorkspace(root)

            series = workspace.list_series()

            self.assertEqual([item.id for item in series], ["course-a", "course-b"])
            self.assertEqual([video.id for video in series[0].videos], ["a1", "a2"])
            self.assertEqual(series[0].videos[0].status, "pending")
            self.assertFalse(series[0].videos[0].processed)
            self.assertEqual(series[0].videos[1].status, "ready")
            self.assertTrue(series[0].videos[1].processed)

    def test_get_video_source_maps_video_and_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "video_include"
            source_path = root / "videos" / "series-a" / "clip-01.mp4"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("video", encoding="utf-8")

            workspace = FileSystemVideoWorkspace(root)

            video = workspace.get_video_source("series-a", "clip-01")

            self.assertIsNotNone(video)
            self.assertEqual(video.source_path, source_path)
            self.assertEqual(video.output_dir, root / "workspace" / "series-a" / "clip-01")
            self.assertFalse(video.processed)

    def test_get_video_summary_reads_workspace_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "video_include"
            summary_dir = root / "workspace" / "series-a" / "clip-01"
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "title": "  ",
                        "chapters": [
                            {
                                "id": "chapter-1",
                                "title": "Intro",
                                "summary": "summary",
                                "key_points": ["point"],
                                "start_seconds": 0.0,
                                "end_seconds": 12.0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (summary_dir / "transcript.cleaned.json").write_text(
                json.dumps(
                    {
                        "segments": [
                            {"start_seconds": 1.0, "end_seconds": 3.0, "text": "第一段"},
                            {"start_seconds": 15.0, "end_seconds": 18.0, "text": "第二段"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            workspace = FileSystemVideoWorkspace(root)

            summary = workspace.get_video_summary("series-a", "clip-01")

            self.assertIsNotNone(summary)
            self.assertEqual(summary.series_id, "series-a")
            self.assertEqual(summary.video_id, "clip-01")
            self.assertEqual(summary.title, "clip-01")
            self.assertEqual(summary.summary["chapters"][0]["transcript_segments"], [
                {"start_seconds": 1.0, "end_seconds": 3.0, "text": "第一段"}
            ])

    def test_get_video_workspace_tools_reflects_summary_and_mindmap_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "video_include"
            source_path = root / "videos" / "series-a" / "clip-01.mp4"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("video", encoding="utf-8")
            output_dir = root / "workspace" / "series-a" / "clip-01"
            output_dir.mkdir(parents=True)
            (output_dir / "summary.json").write_text(json.dumps({"title": "clip-01"}), encoding="utf-8")

            workspace = FileSystemVideoWorkspace(root)

            tools = workspace.get_video_workspace_tools("series-a", "clip-01")

            self.assertIsNotNone(tools)
            self.assertTrue(tools.overview.generated)
            self.assertFalse(tools.mindmap.generated)
            self.assertTrue(tools.mindmap.available)
            self.assertEqual(tools.preview.preview_url, "/api/videos/series-a/clip-01/preview")


if __name__ == "__main__":
    unittest.main()
