"""Persistence adapters available only in the Local product."""

from backend.video_summary.infrastructure.persistence.file_blob_store import FileBlobStore

__all__ = ["FileBlobStore", "ManagedLocalMySql"]


def __getattr__(name: str):
    if name == "ManagedLocalMySql":
        from backend.local.persistence.managed_mysql import ManagedLocalMySql

        return ManagedLocalMySql
    raise AttributeError(name)
