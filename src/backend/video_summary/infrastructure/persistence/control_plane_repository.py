"""MySQL 控制面 Repository。

此模块只承载资源身份和持久任务提交，尚不接管现有文件工作区读取。所有任务
创建、幂等键与 outbox 在同一个 MySQL 事务中提交。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.core.ids import new_ulid
from backend.video_summary.infrastructure.persistence.models import (
    IdempotencyKey,
    Job,
    JobEvent,
    Series,
    Video,
    Workspace,
)


class ControlPlaneConflictError(RuntimeError):
    """幂等键或活跃任务与已持久化状态冲突。"""


@dataclass(frozen=True)
class SubmittedJob:
    id: str
    created: bool
    status: str


class SqlControlPlaneRepository:
    """工作区资源与任务控制面 MySQL 实现。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_workspace(self, *, owner_scope_id: str, title: str) -> str:
        _require_text(owner_scope_id, field_name="owner_scope_id")
        _require_text(title, field_name="workspace title")
        workspace_id = new_ulid()
        with self._session_factory.begin() as session:
            session.add(Workspace(id=workspace_id, owner_scope_id=owner_scope_id, title=title.strip()))
        return workspace_id

    def create_series(
        self,
        *,
        workspace_id: str,
        title: str,
        position: int,
        source_kind: str = "local",
        external_source_url: str | None = None,
    ) -> str:
        _require_text(workspace_id, field_name="workspace_id")
        _require_text(title, field_name="series title")
        if position < 0:
            raise ValueError("Series position cannot be negative.")
        series_id = new_ulid()
        with self._session_factory.begin() as session:
            session.add(
                Series(
                    id=series_id,
                    workspace_id=workspace_id,
                    title=title.strip(),
                    position=position,
                    source_kind=source_kind,
                    external_source_url=external_source_url,
                )
            )
        return series_id

    def create_series_at_next_position(
        self,
        *,
        workspace_id: str,
        title: str,
        source_kind: str = "local",
        external_source_url: str | None = None,
    ) -> str:
        """Create a series after serializing position allocation for one workspace."""

        _require_text(workspace_id, field_name="workspace_id")
        _require_text(title, field_name="series title")
        series_id = new_ulid()
        with self._session_factory.begin() as session:
            workspace = session.get(Workspace, workspace_id, with_for_update=True)
            if workspace is None or workspace.deleted_at is not None:
                raise LookupError(f"workspace not found '{workspace_id}'")
            position = int(
                session.scalar(
                    select(func.coalesce(func.max(Series.position), -1) + 1).where(
                        Series.workspace_id == workspace_id
                    )
                )
            )
            session.add(
                Series(
                    id=series_id,
                    workspace_id=workspace_id,
                    title=title.strip(),
                    position=position,
                    source_kind=source_kind,
                    external_source_url=external_source_url,
                )
            )
        return series_id

    def create_video(
        self,
        *,
        series_id: str,
        title: str,
        source_kind: str,
        external_source_id: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        _require_text(series_id, field_name="series_id")
        _require_text(title, field_name="video title")
        _require_text(source_kind, field_name="source_kind")
        if duration_ms is not None and duration_ms < 0:
            raise ValueError("Video duration cannot be negative.")
        video_id = new_ulid()
        with self._session_factory.begin() as session:
            session.add(
                Video(
                    id=video_id,
                    series_id=series_id,
                    title=title.strip(),
                    source_kind=source_kind,
                    external_source_id=external_source_id,
                    duration_ms=duration_ms,
                )
            )
        return video_id

    def submit_job(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
        operation: str,
        request_payload: dict[str, Any],
        active_key: str | None,
        parent_job_id: str | None = None,
        idempotency_scope_id: str | None = None,
        idempotency_key: str | None = None,
        idempotency_ttl: timedelta = timedelta(days=1),
    ) -> SubmittedJob:
        _require_text(workspace_id, field_name="workspace_id")
        _require_text(resource_type, field_name="resource_type")
        _require_text(resource_id, field_name="resource_id")
        _require_text(operation, field_name="operation")
        if (idempotency_scope_id is None) != (idempotency_key is None):
            raise ValueError("idempotency_scope_id and idempotency_key must be supplied together.")
        request_hash = _request_hash(request_payload)
        job_id = new_ulid()
        try:
            with self._session_factory.begin() as session:
                existing = self._find_idempotent_job(
                    session,
                    scope_id=idempotency_scope_id,
                    key=idempotency_key,
                    request_hash=request_hash,
                )
                if existing is not None:
                    return existing
                if parent_job_id is not None:
                    parent = session.get(Job, parent_job_id)
                    if parent is None or parent.workspace_id != workspace_id:
                        raise ValueError("parent_job_id must reference a Job in the same Workspace.")
                job = Job(
                    id=job_id,
                    workspace_id=workspace_id,
                    parent_job_id=parent_job_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    operation=operation,
                    status="queued",
                    request_payload=request_payload,
                    active_key=active_key,
                )
                session.add(job)
                # IdempotencyKey has a direct FK to jobs but no ORM relationship.
                # Flush now so MySQL always sees the parent row before the key row.
                session.flush()
                session.add(
                    JobEvent(
                        id=new_ulid(),
                        job_id=job_id,
                        sequence=1,
                        stage="queued",
                        progress=0.0,
                        detail="任务已进入队列",
                    )
                )
                if idempotency_scope_id is not None and idempotency_key is not None:
                    session.add(
                        IdempotencyKey(
                            id=new_ulid(),
                            scope_id=idempotency_scope_id,
                            key=idempotency_key,
                            request_hash=request_hash,
                            job_id=job_id,
                            expires_at=datetime.now(timezone.utc) + idempotency_ttl,
                        )
                    )
            return SubmittedJob(id=job_id, created=True, status="queued")
        except IntegrityError as error:
            if idempotency_scope_id is not None:
                existing = self._existing_idempotency_result(
                    scope_id=idempotency_scope_id,
                    key=idempotency_key,
                    request_hash=request_hash,
                )
                if existing is not None:
                    return existing
                raise ControlPlaneConflictError("An idempotency key conflict occurred; retry the request.") from error
            if active_key is not None:
                raise ControlPlaneConflictError("An active job already exists for this resource.") from error
            raise

    @staticmethod
    def _find_idempotent_job(
        session: Session,
        *,
        scope_id: str | None,
        key: str | None,
        request_hash: str,
    ) -> SubmittedJob | None:
        if scope_id is None or key is None:
            return None
        record = session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.scope_id == scope_id, IdempotencyKey.key == key).with_for_update()
        )
        if record is None:
            return None
        if record.expires_at <= datetime.now(timezone.utc):
            session.delete(record)
            session.flush()
            return None
        if record.request_hash != request_hash:
            raise ControlPlaneConflictError("Idempotency key was reused with a different request.")
        job = session.get(Job, record.job_id)
        if job is None:
            raise RuntimeError("Idempotency record references a missing job.")
        return SubmittedJob(id=job.id, created=False, status=job.status)

    def _existing_idempotency_result(
        self,
        *,
        scope_id: str,
        key: str | None,
        request_hash: str,
    ) -> SubmittedJob | None:
        if key is None:
            return None
        with self._session_factory() as session:
            record = session.scalar(
                select(IdempotencyKey).where(IdempotencyKey.scope_id == scope_id, IdempotencyKey.key == key)
            )
            if record is None or record.expires_at <= datetime.now(timezone.utc):
                return None
            if record.request_hash != request_hash:
                raise ControlPlaneConflictError("Idempotency key was reused with a different request.")
            job = session.get(Job, record.job_id)
            if job is None:
                raise RuntimeError("Idempotency record references a missing job.")
            return SubmittedJob(id=job.id, created=False, status=job.status)


def _request_hash(payload: dict[str, Any]) -> str:
    try:
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError("Job request payload must be JSON serializable.") from error
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _require_text(value: str, *, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} is required.")
