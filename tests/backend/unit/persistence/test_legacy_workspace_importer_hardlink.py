from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.local.persistence.file_blob_store import FileBlobStore
from backend.local.persistence.legacy_workspace_importer import LegacyWorkspaceImporter


class RecordingSessions:
    def __init__(self) -> None:
        self.media = None

    def __call__(self):
        return self

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalar(self, _query):
        return None

    def add(self, media) -> None:
        self.media = media


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

            importer._import_media("video-1", source_path)

            blob_path = root / "runtime" / "blobs" / "objects" / "media" / "video-1" / "source.mp4"
            self.assertTrue(source_path.samefile(blob_path))
            self.assertEqual(sessions.media.blob_key, "media/video-1/source.mp4")
