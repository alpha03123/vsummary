"""Persistence adapters available only in the Local product."""

from backend.local.persistence.file_blob_store import FileBlobStore
from backend.local.persistence.managed_mysql import ManagedLocalMySql

__all__ = ["FileBlobStore", "ManagedLocalMySql"]
