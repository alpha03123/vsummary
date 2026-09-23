from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from backend.local.persistence.file_blob_store import FileBlobStore
from backend.local.persistence.legacy_workspace_importer import LegacyWorkspaceImporter
from backend.video_summary.infrastructure.persistence.models import ExternalMediaReference, MediaObject


class RecordingSessions:
    def __init__(self) -> None:
        self.media = None
        self.existing_media = None
        self.query_result = None
        self.rows = []

    def __call__(self):
        return self

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalar(self, _query):
        return self.existing_media

    def execute(self, _query, _parameters):
        return SimpleNamespace(scalar=lambda: self.query_result)

    def get(self, _model, _key):
        return None

    def add(self, row) -> None:
        self.rows.append(row)
        if isinstance(row, MediaObject):
            self.media = row


class LegacyWorkspaceImporterHardlinkTests(unittest.TestCase):
    def test_same_volume_import_preserves_source_and_shares_blob_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "videos" / "series-1" / "lesson.mp4"
            source_path.parent.mkdir(parents=True)
            source_path.write_bytes(b"legacy video")
            sessions = RecordingSessions()
            store = FileBlobStore(root / "runtime" / "blobs")
            importer = LegacyWorkspaceImporter(root_dir=root, session_factory=sessions, blob_store=store)

            importer._import_media("video-1", source_path, storage_mode="hardlink")

            blob_path = root / "runtime" / "blobs" / "objects" / "media" / "video-1" / "source.mp4"
            self.assertTrue(source_path.samefile(blob_path))
            self.assertEqual(sessions.media.blob_key, "media/video-1/source.mp4")

    def test_copy_mode_keeps_an_independent_blob(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "lesson.mp4"
            source_path.write_bytes(b"legacy video")
            store = FileBlobStore(root / "blobs")
            importer = LegacyWorkspaceImporter(root_dir=root, session_factory=RecordingSessions(), blob_store=store)

            importer._import_media("video-1", source_path, storage_mode="copy")

            blob_path = root / "blobs" / "objects" / "media" / "video-1" / "source.mp4"
            self.assertFalse(source_path.samefile(blob_path))
            self.assertEqual(blob_path.read_bytes(), source_path.read_bytes())

    def test_existing_copy_is_replaced_with_hardlink_for_legacy_hardlink_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "lesson.mp4"
            source_path.write_bytes(b"legacy video")
            store = FileBlobStore(root / "blobs")
            sessions = RecordingSessions()
            importer = LegacyWorkspaceImporter(root_dir=root, session_factory=sessions, blob_store=store)
            importer._import_media("video-1", source_path, storage_mode="copy")
            sessions.existing_media = sessions.media

            importer._import_media("video-1", source_path, storage_mode="hardlink")

            blob_path = root / "blobs" / "objects" / "media" / "video-1" / "source.mp4"
            self.assertTrue(source_path.samefile(blob_path))

    def test_existing_hardlink_is_replaced_with_copy_for_legacy_copy_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "lesson.mp4"
            source_path.write_bytes(b"legacy video")
            store = FileBlobStore(root / "blobs")
            sessions = RecordingSessions()
            importer = LegacyWorkspaceImporter(root_dir=root, session_factory=sessions, blob_store=store)
            importer._import_media("video-1", source_path, storage_mode="hardlink")
            sessions.existing_media = sessions.media

            importer._import_media("video-1", source_path, storage_mode="copy")

            blob_path = root / "blobs" / "objects" / "media" / "video-1" / "source.mp4"
            self.assertFalse(source_path.samefile(blob_path))
            self.assertEqual(blob_path.read_bytes(), source_path.read_bytes())

    def test_external_reference_reads_old_source_json_without_copying_media(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            series_dir = root / "workspace" / "series-1"
            video_dir = series_dir / "lesson"
            video_dir.mkdir(parents=True)
            (series_dir / "series_meta.json").write_text(
                json.dumps({"title": "Series", "storage_mode": "external_reference"}), encoding="utf-8"
            )
            external_path = root / "outside" / "lesson.mp4"
            source_file = video_dir / "source.json"
            source_file.write_text(json.dumps({"source_path": str(external_path)}), encoding="utf-8")
            sessions = RecordingSessions()
            importer = LegacyWorkspaceImporter(root_dir=root, session_factory=sessions, blob_store=FileBlobStore(root / "blobs"))

            self.assertEqual(importer._legacy_storage_mode("series-1"), "external_reference")
            self.assertEqual(importer._read_external_source(source_file), external_path)
            importer._import_external_media("video-1", source_file)
            references = [row for row in sessions.rows if isinstance(row, ExternalMediaReference)]
            self.assertEqual(len(references), 1)
            self.assertEqual(references[0].source_path, str(external_path))
            self.assertFalse((root / "blobs").exists())

    def test_linked_series_external_source_is_not_skipped(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_dir = root / "workspace" / "linked-series" / "video-1"
            video_dir.mkdir(parents=True)
            source_file = video_dir / "source.json"
            source_file.write_text(json.dumps({"source_path": str(root / "outside.mp4")}), encoding="utf-8")
            sessions = RecordingSessions()
            sessions.query_result = "sql-video-1"
            importer = LegacyWorkspaceImporter(root_dir=root, session_factory=sessions, blob_store=FileBlobStore(root / "blobs"))
            importer._mapped = Mock(return_value=SimpleNamespace(target_id="sql-series-1"))
            importer._import_external_media = Mock()
            importer._import_video_records = Mock(return_value=1)

            imported_content = importer._import_linked_external_sources("workspace-1", "linked-series")

            self.assertEqual(imported_content, 1)
            importer._import_external_media.assert_called_once_with("sql-video-1", source_file)
