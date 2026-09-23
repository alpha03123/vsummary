from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock

from backend.local.persistence.file_blob_store import FileBlobStore
from backend.video_summary.infrastructure.persistence.models import ExternalMediaReference, MediaObject
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace


class SqlWorkspaceStorageModeTests(unittest.TestCase):
    def _workspace(self, root: Path) -> tuple[SqlVideoWorkspace, MagicMock]:
        sessions = MagicMock()
        sessions.return_value.__enter__.return_value.execute.return_value.scalar.return_value = "series-1"
        workspace = SqlVideoWorkspace(
            session_factory=sessions,
            blob_store=FileBlobStore(root / "blobs"),
            cache_root=root / "cache",
            workspace_id="workspace-1",
        )
        workspace._control = Mock()
        workspace._control.create_video.return_value = "video-1"
        return workspace, sessions

    def test_external_reference_records_only_the_original_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "lesson.mp4"
            source_path.write_bytes(b"video")
            workspace, sessions = self._workspace(root)

            workspace._import_paths("series-1", [source_path], storage_mode="external_reference")

            row = sessions.begin.return_value.__enter__.return_value.add.call_args.args[0]
            self.assertIsInstance(row, ExternalMediaReference)
            self.assertEqual(row.source_path, str(source_path))
            self.assertFalse((root / "blobs").exists())

    def test_hardlink_import_shares_the_source_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "lesson.mp4"
            source_path.write_bytes(b"video")
            workspace, sessions = self._workspace(root)

            workspace._import_paths("series-1", [source_path], storage_mode="hardlink")

            row = sessions.begin.return_value.__enter__.return_value.add.call_args.args[0]
            self.assertIsInstance(row, MediaObject)
            blob_path = root / "blobs" / "objects" / "media" / "video-1" / "source.mp4"
            self.assertTrue(source_path.samefile(blob_path))

    def test_relink_updates_external_path_without_copying_video(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "replacement.mp4"
            source_path.write_bytes(b"video")
            workspace, sessions = self._workspace(root)
            external = SimpleNamespace(source_path="C:/missing.mp4")
            sessions.begin.return_value.__enter__.return_value.get.return_value = external

            workspace.relink_external_video(series_id="series-1", video_id="video-1", source_path=source_path)

            self.assertEqual(external.source_path, str(source_path))
            self.assertFalse((root / "blobs").exists())
