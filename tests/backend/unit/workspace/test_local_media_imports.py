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

    def test_import_local_series_from_paths_creates_hardlinks_and_persists_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            source_path = root_dir / "source.mp4"
            source_path.write_bytes(b"video")
            workspace = FileSystemVideoWorkspace(root_dir)

            series = workspace.import_local_series_from_paths(
                title="Hardlink Course",
                source_paths=[source_path],
                storage_mode="hardlink",
            )

            imported_path = root_dir / "videos" / series.id / source_path.name
            self.assertEqual(source_path.stat().st_ino, imported_path.stat().st_ino)
            self.assertEqual(2, imported_path.stat().st_nlink)
            self.assertIn('"storage_mode": "hardlink"', (root_dir / "workspace" / series.id / "series_meta.json").read_text(encoding="utf-8"))

    def test_append_from_paths_inherits_hardlink_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            first_source = root_dir / "first.mp4"
            second_source = root_dir / "second.mp4"
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")
            workspace = FileSystemVideoWorkspace(root_dir)
            series = workspace.import_local_series_from_paths(
                title="Hardlink Course",
                source_paths=[first_source],
                storage_mode="hardlink",
            )

            workspace.import_local_series_videos_from_paths(
                series_id=series.id,
                source_paths=[second_source],
            )

            imported_path = root_dir / "videos" / series.id / second_source.name
            self.assertEqual(second_source.stat().st_ino, imported_path.stat().st_ino)

    def test_legacy_series_defaults_to_copy_for_path_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            source_path = root_dir / "source.mp4"
            source_path.write_bytes(b"video")
            workspace = FileSystemVideoWorkspace(root_dir)
            series = workspace.import_local_series(
                title="Legacy Course",
                files=[("first.mp4", io.BytesIO(b"first"))],
            )
            meta_path = root_dir / "workspace" / series.id / "series_meta.json"
            meta_path.write_text('{"title": "Legacy Course"}', encoding="utf-8")

            workspace.import_local_series_videos_from_paths(
                series_id=series.id,
                source_paths=[source_path],
            )

            imported_path = root_dir / "videos" / series.id / source_path.name
            self.assertNotEqual(source_path.stat().st_ino, imported_path.stat().st_ino)


if __name__ == "__main__":
    unittest.main()
