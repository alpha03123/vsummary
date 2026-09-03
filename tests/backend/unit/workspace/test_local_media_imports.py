from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.video_summary.infrastructure.storage.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


class LocalMediaImportTests(unittest.TestCase):
    def test_renaming_local_series_and_video_preserves_stable_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            workspace = FileSystemVideoWorkspace(root_dir)
            source_path = root_dir / "original-video.mp4"
            source_path.write_bytes(b"video")
            series = workspace.import_local_series_from_paths(
                title="Original Series",
                source_paths=[source_path],
                storage_mode="copy",
            )

            self.assertTrue(workspace.rename_series(series.id, "Renamed Series"))
            self.assertTrue(workspace.rename_video(series.id, "original-video", "Renamed Video"))

            listed_series = next(item for item in workspace.list_series() if item.id == series.id)
            self.assertEqual(listed_series.title, "Renamed Series")
            self.assertEqual(listed_series.videos[0].id, "original-video")
            self.assertEqual(listed_series.videos[0].title, "Renamed Video")
            source = workspace.get_video_source(series.id, "original-video")
            self.assertIsNotNone(source)
            self.assertEqual(source.title, "Renamed Video")
            self.assertTrue((root_dir / "videos" / series.id / "original-video.mp4").exists())

    def test_renaming_linked_series_and_video_updates_link_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = FileSystemVideoWorkspace(Path(temp_dir))
            workspace.save_linked_series(
                LinkedSeries(
                    series_id="linked-series",
                    title="Original Linked Series",
                    cover_url="",
                    source_url="",
                    videos=[
                        LinkedVideo(
                            bvid="BV1example",
                            page=1,
                            title="Original Linked Video",
                            cover_url="",
                            duration_seconds=0,
                            source_url="",
                        )
                    ],
                )
            )

            self.assertTrue(workspace.rename_series("linked-series", "Renamed Linked Series"))
            self.assertTrue(workspace.rename_video("linked-series", "BV1example", "Renamed Linked Video"))

            listed_series = next(item for item in workspace.list_series() if item.id == "linked-series")
            self.assertEqual(listed_series.title, "Renamed Linked Series")
            self.assertEqual(listed_series.videos[0].title, "Renamed Linked Video")

    def test_import_local_series_accepts_audio_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            source_path = root_dir / "lesson-1.mp3"
            source_path.write_bytes(b"audio")
            workspace = FileSystemVideoWorkspace(root_dir)

            series = workspace.import_local_series_from_paths(
                title="Audio Course",
                source_paths=[source_path],
                storage_mode="copy",
            )

            self.assertEqual(series.videos[0].id, "lesson-1")
            self.assertEqual(series.videos[0].source_name, "lesson-1.mp3")
            self.assertEqual(series.videos[0].source_type, "audio")
            source = workspace.get_video_source(series.id, "lesson-1")
            self.assertIsNotNone(source)
            self.assertEqual(source.source_type, "audio")

    def test_import_local_series_rejects_duplicate_media_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            first = root_dir / "lesson-1.mp4"
            second = root_dir / "lesson-1.mp3"
            first.write_bytes(b"video")
            second.write_bytes(b"audio")
            workspace = FileSystemVideoWorkspace(root_dir)

            with self.assertRaisesRegex(ValueError, "重复媒体名"):
                workspace.import_local_series_from_paths(
                    title="Mixed Course",
                    source_paths=[first, second],
                    storage_mode="copy",
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
            first_source = root_dir / "first.mp4"
            first_source.write_bytes(b"first")
            workspace = FileSystemVideoWorkspace(root_dir)
            series = workspace.import_local_series_from_paths(
                title="Legacy Course",
                source_paths=[first_source],
                storage_mode="copy",
            )
            meta_path = root_dir / "workspace" / series.id / "series_meta.json"
            meta_path.write_text('{"title": "Legacy Course"}', encoding="utf-8")

            workspace.import_local_series_videos_from_paths(
                series_id=series.id,
                source_paths=[source_path],
            )

            imported_path = root_dir / "videos" / series.id / source_path.name
            self.assertNotEqual(source_path.stat().st_ino, imported_path.stat().st_ino)

    def test_external_reference_keeps_media_outside_the_workspace_and_deletion_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            source_dir = root_dir / "nas"
            source_dir.mkdir()
            source_path = source_dir / "lesson.mp4"
            source_path.write_bytes(b"video")
            workspace = FileSystemVideoWorkspace(root_dir)

            series = workspace.import_local_series_from_paths(
                title="NAS Course",
                source_paths=[source_path],
                storage_mode="external_reference",
            )

            self.assertFalse((root_dir / "videos" / series.id / source_path.name).exists())
            source = workspace.get_video_source(series.id, "lesson")
            self.assertIsNotNone(source)
            self.assertEqual(source_path, source.source_path)
            self.assertTrue((root_dir / "workspace" / series.id / "lesson" / "source.json").is_file())

            self.assertTrue(workspace.delete_video(series.id, "lesson"))
            self.assertTrue(source_path.is_file())

    def test_external_reference_append_inherits_series_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            first_source = root_dir / "first.mp4"
            second_source = root_dir / "second.mp4"
            first_source.write_bytes(b"first")
            second_source.write_bytes(b"second")
            workspace = FileSystemVideoWorkspace(root_dir)
            series = workspace.import_local_series_from_paths(
                title="NAS Course",
                source_paths=[first_source],
                storage_mode="external_reference",
            )

            workspace.import_local_series_videos_from_paths(series_id=series.id, source_paths=[second_source])

            listed = next(item for item in workspace.list_series() if item.id == series.id)
            self.assertEqual(["first", "second"], [video.id for video in listed.videos])
            self.assertTrue(second_source.is_file())

    def test_external_reference_marks_missing_source_and_can_be_relinked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            source_path = root_dir / "original" / "lesson.mp4"
            source_path.parent.mkdir()
            source_path.write_bytes(b"video")
            workspace = FileSystemVideoWorkspace(root_dir)
            series = workspace.import_local_series_from_paths(
                title="NAS Course",
                source_paths=[source_path],
                storage_mode="external_reference",
            )
            source_path.unlink()

            listed = next(item for item in workspace.list_series() if item.id == series.id)
            self.assertEqual("source_missing", listed.videos[0].status)
            tools = workspace.get_video_workspace_tools(series.id, "lesson")
            self.assertIsNotNone(tools)
            self.assertFalse(tools.overview.available)
            self.assertEqual("source_missing", tools.preview.status)
            self.assertIsNone(tools.preview.preview_url)

            replacement = root_dir / "moved" / "lesson.mp4"
            replacement.parent.mkdir()
            replacement.write_bytes(b"replacement")
            workspace.relink_external_video(series_id=series.id, video_id="lesson", source_path=replacement)

            relinked = next(item for item in workspace.list_series() if item.id == series.id)
            self.assertEqual("pending", relinked.videos[0].status)
            self.assertEqual(replacement, workspace.get_video_source(series.id, "lesson").source_path)


if __name__ == "__main__":
    unittest.main()
