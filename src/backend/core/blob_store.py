"""Blob storage contract used by Core persistence services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


class BlobStoreError(RuntimeError):
    """Blob object is missing, corrupt, or cannot be safely addressed."""


@dataclass(frozen=True)
class BlobReference:
    key: str
    sha256: str
    byte_size: int
    content_type: str


@dataclass(frozen=True)
class StagedBlob:
    job_id: str
    token: str
    sha256: str
    byte_size: int
    content_type: str


class BlobStore(Protocol):
    def put_staging(self, *, job_id: str, source: BinaryIO, content_type: str) -> StagedBlob: ...

    def put_staging_hardlink(self, *, job_id: str, source_path: Path, content_type: str) -> StagedBlob: ...

    def can_hardlink(self, source_path: Path) -> bool: ...

    def shares_file(self, reference: BlobReference, source_path: Path) -> bool: ...

    def replace(self, staged: StagedBlob, existing: BlobReference) -> BlobReference: ...

    def commit(self, staged: StagedBlob, *, object_key: str) -> BlobReference: ...

    def open(self, reference: BlobReference) -> BinaryIO: ...

    def materialize(self, reference: BlobReference, *, task_dir: Path, filename: str) -> Path: ...

    def delete(self, reference: BlobReference) -> None: ...

    def discard_staging(self, staged: StagedBlob) -> None: ...
