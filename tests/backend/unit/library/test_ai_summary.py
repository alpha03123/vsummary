from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.video_summary.infrastructure.storage.filesystem_video_workspace import FileSystemVideoWorkspace


class VideoAiSummaryStorageTests(unittest.TestCase):
    def test_replaces_unique_ai_summary_without_writing_personal_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video_path = root / "video.mp4"
            video_path.write_bytes(b"video")
            workspace = FileSystemVideoWorkspace(root)
            series = workspace.import_local_series_from_paths(
                title="series-1",
                source_paths=[video_path],
                storage_mode="copy",
            )

            first = workspace.save_video_ai_summary(series.id, "video", title="第一次", content="内容一")
            second = workspace.save_video_ai_summary(series.id, "video", title="第二次", content="内容二")

            self.assertEqual("第二次", second.title)
            self.assertEqual("内容二", workspace.get_video_ai_summary(series.id, "video").content)
            self.assertEqual(first.created_at, second.created_at)
            self.assertEqual([], workspace.get_video_notes(series.id, "video").notes)

    def test_migrates_latest_legacy_agent_note_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video_path = root / "video.mp4"
            video_path.write_bytes(b"video")
            workspace = FileSystemVideoWorkspace(root)
            series = workspace.import_local_series_from_paths(title="series-1", source_paths=[video_path], storage_mode="copy")
            output_dir = root / "workspace" / series.id / "video"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "notes.json").write_text(
                '{"notes":[{"id":"old","title":"旧 AI","content":"旧内容","source":"agent","created_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}]}',
                encoding="utf-8",
            )

            summary = workspace.get_video_ai_summary(series.id, "video")

            self.assertEqual("旧 AI", summary.title)
            self.assertTrue((output_dir / "ai_summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
