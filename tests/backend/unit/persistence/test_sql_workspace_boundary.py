from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock

from backend.core.blob_store import BlobStoreError
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace


class SqlVideoWorkspaceBoundaryTests(unittest.TestCase):
    def test_requires_an_explicit_workspace_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace_id"):
            SqlVideoWorkspace(
                session_factory=Mock(),
                blob_store=Mock(),
                cache_root=Path("cache"),
                workspace_id="",
            )

    def test_binds_the_composition_workspace_id(self) -> None:
        workspace = SqlVideoWorkspace(
            session_factory=Mock(),
            blob_store=Mock(),
            cache_root=Path("cache"),
            workspace_id="workspace-1",
        )

        self.assertEqual(workspace.workspace_id, "workspace-1")

    def test_missing_artifact_blob_is_reported_as_unavailable(self) -> None:
        sessions = MagicMock()
        session = sessions.return_value.__enter__.return_value
        session.execute.return_value.mappings.return_value.first.return_value = {
            "blob_key": "artifacts/video-1/note_frame/10.jpg",
            "sha256": "a" * 64,
            "byte_size": 1,
            "media_type": "image/jpeg",
        }
        blobs = Mock()
        blobs.materialize.side_effect = BlobStoreError("Committed blob does not exist.")
        workspace = SqlVideoWorkspace(
            session_factory=sessions,
            blob_store=blobs,
            cache_root=Path("cache"),
            workspace_id="workspace-1",
        )

        self.assertIsNone(workspace.materialize_artifact(video_id="video-1", kind="note_frame", filename="10.jpg"))

    def test_logs_the_actual_error_when_video_source_blob_is_unavailable(self) -> None:
        sessions = MagicMock()
        session = sessions.return_value.__enter__.return_value
        session.execute.return_value.mappings.return_value.first.return_value = {
            "id": "video-1",
            "title": "Video",
            "source_kind": "video",
            "content_version": 1,
            "blob_key": "media/video-1/source.mp4",
            "sha256": "a" * 64,
            "byte_size": 1,
            "media_type": "video/mp4",
            "external_path": None,
        }
        blobs = Mock()
        blobs.materialize.side_effect = BlobStoreError("Committed blob does not exist.")
        workspace = SqlVideoWorkspace(
            session_factory=sessions,
            blob_store=blobs,
            cache_root=Path("cache"),
            workspace_id="workspace-1",
        )

        with self.assertLogs(
            "backend.video_summary.infrastructure.persistence.sql_video_workspace", level="ERROR"
        ) as logs:
            self.assertIsNone(workspace.get_video_source("series-1", "video-1"))

        self.assertIn("failed to materialize video source", logs.output[0])
        self.assertIn("BlobStoreError: Committed blob does not exist.", logs.output[0])

    def test_external_video_source_uses_the_original_path_without_materializing(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "lesson.mp4"
            source_path.write_bytes(b"video")
            sessions = MagicMock()
            session = sessions.return_value.__enter__.return_value
            session.execute.return_value.mappings.return_value.first.return_value = {
                "id": "video-1",
                "title": "Lesson",
                "source_kind": "video",
                "content_version": 0,
                "blob_key": None,
                "external_path": str(source_path),
            }
            blobs = Mock()
            workspace = SqlVideoWorkspace(
                session_factory=sessions,
                blob_store=blobs,
                cache_root=Path(temp_dir) / "cache",
                workspace_id="workspace-1",
            )

            source = workspace.get_video_source("series-1", "video-1")

            self.assertEqual(source.source_path, source_path)
            blobs.materialize.assert_not_called()
