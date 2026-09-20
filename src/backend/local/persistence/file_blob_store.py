"""受控二进制对象存储。

本地实现使用用户数据目录；接口形状与未来对象存储适配器一致。业务层只持有
对象键和校验信息，FFmpeg/ASR 必须通过 ``materialize`` 获得任务临时路径。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4


from backend.core.blob_store import BlobReference, BlobStoreError, StagedBlob


COPY_BUFFER_SIZE = 1_048_576
MAX_OBJECT_KEY_LENGTH = 512


class FileBlobStore:
    """本地用户数据目录中的 BlobStore。

    staging 和 committed 对象位于同一个根目录下，提交使用 ``os.replace``，
    因而同卷内的文件发布是原子的。调用者不能把客户端路径或绝对路径当作
    对象键传入。
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._objects_root = root / "objects"
        self._staging_root = root / "staging"

    def put_staging(self, *, job_id: str, source: BinaryIO, content_type: str) -> StagedBlob:
        """把二进制流写入仅属于某个 job 的 staging 对象。"""

        _validate_identifier(job_id, field_name="job_id")
        if not content_type.strip():
            raise BlobStoreError("Blob content type is required.")
        token = uuid4().hex
        target = self._staging_path(job_id, token)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with target.open("xb") as output:
                while chunk := source.read(COPY_BUFFER_SIZE):
                    if not isinstance(chunk, bytes):
                        raise BlobStoreError("Blob source must return bytes.")
                    output.write(chunk)
                    digest.update(chunk)
                    byte_size += len(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return StagedBlob(
            job_id=job_id,
            token=token,
            sha256=digest.hexdigest(),
            byte_size=byte_size,
            content_type=content_type.strip(),
        )

    def commit(self, staged: StagedBlob, *, object_key: str) -> BlobReference:
        """校验 staging 对象后原子发布到服务端生成的对象键。"""

        source = self._staging_path(staged.job_id, staged.token)
        if not source.is_file():
            raise BlobStoreError("Staged blob does not exist.")
        actual = _stat_file(source, staged.content_type)
        if actual.sha256 != staged.sha256 or actual.byte_size != staged.byte_size:
            raise BlobStoreError("Staged blob checksum does not match its recorded value.")
        target = self._object_path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = _stat_file(target, staged.content_type)
            if existing.sha256 != staged.sha256 or existing.byte_size != staged.byte_size:
                raise BlobStoreError("Object key already exists with different content.")
            source.unlink(missing_ok=True)
            return BlobReference(object_key, existing.sha256, existing.byte_size, staged.content_type)
        os.replace(source, target)
        return BlobReference(object_key, actual.sha256, actual.byte_size, staged.content_type)

    def open(self, reference: BlobReference) -> BinaryIO:
        """以只读二进制流打开已提交对象。"""

        path = self._object_path(reference.key)
        if not path.is_file():
            raise BlobStoreError("Committed blob does not exist.")
        return path.open("rb")

    def materialize(self, reference: BlobReference, *, task_dir: Path, filename: str) -> Path:
        """将对象复制为任务本地文件，供只接受 ``Path`` 的媒体工具使用。"""

        _validate_filename(filename)
        source = self._object_path(reference.key)
        if not source.is_file():
            raise BlobStoreError("Committed blob does not exist.")
        target = task_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file():
                raise BlobStoreError("Materialized blob target is not a file.")
            existing = _stat_file(target, reference.content_type)
            if existing.sha256 == reference.sha256 and existing.byte_size == reference.byte_size:
                return target
            target.unlink()
        shutil.copyfile(source, target)
        actual = _stat_file(target, reference.content_type)
        if actual.sha256 != reference.sha256 or actual.byte_size != reference.byte_size:
            target.unlink(missing_ok=True)
            raise BlobStoreError("Materialized blob checksum verification failed.")
        return target

    def stat(self, reference: BlobReference) -> BlobReference:
        """读取并重新计算已提交对象的完整性信息。"""

        path = self._object_path(reference.key)
        if not path.is_file():
            raise BlobStoreError("Committed blob does not exist.")
        return _stat_file(path, reference.content_type, key=reference.key)

    def delete(self, reference: BlobReference) -> None:
        """删除已提交对象；调用方必须先完成数据库删除状态切换。"""

        self._object_path(reference.key).unlink(missing_ok=True)

    def discard_staging(self, staged: StagedBlob) -> None:
        """删除失败或取消任务的 staging 对象。"""

        self._staging_path(staged.job_id, staged.token).unlink(missing_ok=True)

    def _staging_path(self, job_id: str, token: str) -> Path:
        _validate_identifier(job_id, field_name="job_id")
        _validate_identifier(token, field_name="staging token")
        return self._staging_root / job_id / token

    def _object_path(self, object_key: str) -> Path:
        parts = _safe_object_key_parts(object_key)
        return self._objects_root.joinpath(*parts)


def _stat_file(path: Path, content_type: str, *, key: str | None = None) -> BlobReference:
    digest = hashlib.sha256()
    byte_size = 0
    with path.open("rb") as source:
        while chunk := source.read(COPY_BUFFER_SIZE):
            digest.update(chunk)
            byte_size += len(chunk)
    return BlobReference(key or path.name, digest.hexdigest(), byte_size, content_type)


def _safe_object_key_parts(value: str) -> tuple[str, ...]:
    if not value or len(value) > MAX_OBJECT_KEY_LENGTH or value.startswith("/") or "\\" in value:
        raise BlobStoreError("Blob object key must be a non-absolute POSIX relative path.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BlobStoreError("Blob object key contains an unsafe path segment.")
    return tuple(path.parts)


def _validate_identifier(value: str, *, field_name: str) -> None:
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in value):
        raise BlobStoreError(f"Blob {field_name} is invalid.")


def _validate_filename(value: str) -> None:
    if not value or Path(value).name != value or value in {".", ".."}:
        raise BlobStoreError("Materialized blob filename is invalid.")
