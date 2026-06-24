from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from backend.video_summary.infrastructure.storage.filesystem_video_workspace import FileSystemVideoWorkspace


class LocalMediaImportTests(unittest.TestCase):
    def test_import_local_series_accepts_audio_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = FileSystemVideoWorkspace(Path(temp_dir))

            series = workspace.import_local_series(
                title="Audio Course",
                files=[("lesson-1.mp3", io.BytesIO(b"audio"))],
            )

            self.assertEqual(series.videos[0].id, "lesson-1")
            self.assertEqual(series.videos[0].source_name, "lesson-1.mp3")
            self.assertEqual(series.videos[0].source_type, "audio")
            source = workspace.get_video_source(series.id, "lesson-1")
            self.assertIsNotNone(source)
            self.assertEqual(source.source_type, "audio")

    def test_import_local_series_rejects_duplicate_media_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = FileSystemVideoWorkspace(Path(temp_dir))

            with self.assertRaisesRegex(ValueError, "重复媒体名"):
                workspace.import_local_series(
                    title="Mixed Course",
                    files=[
                        ("lesson-1.mp4", io.BytesIO(b"video")),
                        ("lesson-1.mp3", io.BytesIO(b"audio")),
                    ],
                )


if __name__ == "__main__":
    unittest.main()
