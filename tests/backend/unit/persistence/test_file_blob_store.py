from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.core.blob_store import BlobStoreError
from backend.local.persistence.file_blob_store import FileBlobStore


class FileBlobStoreTests(unittest.TestCase):
    def test_stage_commit_stat_and_materialize_preserve_bytes_and_checksum(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = FileBlobStore(root / "blobs")
            payload = b"video source bytes"

            staged = store.put_staging(job_id="job_123", source=BytesIO(payload), content_type="video/mp4")
            reference = store.commit(staged, object_key="workspace-1/video-1/source.mp4")
            materialized = store.materialize(reference, task_dir=root / "tasks" / "job_123", filename="source.mp4")

            self.assertEqual(reference.byte_size, len(payload))
            self.assertEqual(store.stat(reference), reference)
            self.assertEqual(materialized.read_bytes(), payload)
            self.assertEqual(
                store.materialize(reference, task_dir=root / "tasks" / "job_123", filename="source.mp4"),
                materialized,
            )
            with store.open(reference) as source:
                self.assertEqual(source.read(), payload)

    def test_hardlink_import_shares_source_and_blob_without_deleting_source(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.mp4"
            source_path.write_bytes(b"video source bytes")
            store = FileBlobStore(root / "blobs")

            staged = store.put_staging_hardlink(
                job_id="job_123", source_path=source_path, content_type="video/mp4"
            )
            reference = store.commit(staged, object_key="media/video-1/source.mp4")
            blob_path = root / "blobs" / "objects" / "media" / "video-1" / "source.mp4"

            self.assertTrue(source_path.samefile(blob_path))
            store.delete(reference)
            self.assertEqual(source_path.read_bytes(), b"video source bytes")
            self.assertFalse(blob_path.exists())

    def test_removing_legacy_source_keeps_hardlinked_blob(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "legacy.mp4"
            source_path.write_bytes(b"legacy video")
            store = FileBlobStore(root / "blobs")

            staged = store.put_staging_hardlink(
                job_id="legacy_123", source_path=source_path, content_type="video/mp4"
            )
            reference = store.commit(staged, object_key="media/video-1/source.mp4")
            source_path.unlink()

            with store.open(reference) as blob:
                self.assertEqual(blob.read(), b"legacy video")

    def test_repeating_same_commit_key_with_same_content_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = FileBlobStore(Path(temp_dir) / "blobs")
            first = store.put_staging(job_id="job_123", source=BytesIO(b"same"), content_type="text/plain")
            second = store.put_staging(job_id="job_456", source=BytesIO(b"same"), content_type="text/plain")

            committed = store.commit(first, object_key="exports/summary.md")
            repeated = store.commit(second, object_key="exports/summary.md")

            self.assertEqual(repeated, committed)

    def test_existing_key_with_different_content_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = FileBlobStore(Path(temp_dir) / "blobs")
            first = store.put_staging(job_id="job_123", source=BytesIO(b"first"), content_type="text/plain")
            second = store.put_staging(job_id="job_456", source=BytesIO(b"second"), content_type="text/plain")
            store.commit(first, object_key="exports/summary.md")

            with self.assertRaisesRegex(BlobStoreError, "different content"):
                store.commit(second, object_key="exports/summary.md")

    def test_rejects_path_traversal_and_absolute_object_keys(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = FileBlobStore(Path(temp_dir) / "blobs")
            staged = store.put_staging(job_id="job_123", source=BytesIO(b"data"), content_type="text/plain")

            for key in ("../outside", "/absolute", "workspace\\video", "a/../../b"):
                with self.subTest(key=key), self.assertRaises(BlobStoreError):
                    store.commit(staged, object_key=key)

    def test_rejects_object_key_that_cannot_be_uniquely_indexed_in_mysql(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = FileBlobStore(Path(temp_dir) / "blobs")
            staged = store.put_staging(job_id="job_123", source=BytesIO(b"data"), content_type="text/plain")

            with self.assertRaises(BlobStoreError):
                store.commit(staged, object_key="a" * 513)

    def test_rejects_unsafe_materialized_filename(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = FileBlobStore(root / "blobs")
            staged = store.put_staging(job_id="job_123", source=BytesIO(b"data"), content_type="text/plain")
            reference = store.commit(staged, object_key="exports/data.txt")

            with self.assertRaises(BlobStoreError):
                store.materialize(reference, task_dir=root / "tasks", filename="../outside.txt")
