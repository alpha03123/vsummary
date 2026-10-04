"""Lease context propagated into synchronous persistence and model calls."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from dataclasses import dataclass, field

from sqlalchemy import func, select

from backend.video_summary.infrastructure.persistence.models import Job, Video

if TYPE_CHECKING:
    from backend.video_summary.infrastructure.persistence.job_repository import (
        ClaimedJob,
    )


class JobLeaseLostError(RuntimeError):
    """A stale worker may not mutate authoritative data."""


class ContentVersionConflictError(ValueError):
    """Generation input was edited before the candidate could be saved."""


@dataclass
class ExecutionScope:
    claim: ClaimedJob
    input_versions: dict[str, int] = field(default_factory=dict)


_claim: ContextVar[ExecutionScope | None] = ContextVar("execution_claim", default=None)


@contextmanager
def bind_execution_claim(claim: ClaimedJob):
    token = _claim.set(ExecutionScope(claim))
    try:
        yield
    finally:
        _claim.reset(token)


def current_execution_claim():
    scope = _claim.get()
    return scope.claim if scope is not None else None


def observe_video_version(video_id: str, version: int, *, published: bool = False):
    scope = _claim.get()
    if scope is not None:
        if published:
            scope.input_versions[video_id] = version
        else:
            scope.input_versions.setdefault(video_id, version)


def require_execution_lease(session, workspace_id: str) -> None:
    scope = _claim.get()
    if scope is None:
        return
    claim = scope.claim
    now = session.scalar(select(func.now()))
    job = session.scalar(select(Job).where(Job.id == claim.id).with_for_update())
    if (
        job is None
        or claim.workspace_id != workspace_id
        or job.workspace_id != workspace_id
        or (
            job.status != "running"
            or job.cancel_requested_at is not None
            or job.claimed_by != claim.worker_id
            or job.lease_token != claim.lease_token
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
        )
    ):
        raise JobLeaseLostError("Worker no longer owns an active execution lease.")
    for video_id, expected in sorted(scope.input_versions.items()):
        actual = session.scalar(
            select(Video.content_version).where(Video.id == video_id).with_for_update()
        )
        if actual != expected:
            raise ContentVersionConflictError(
                "Source content changed during generation; stale output cannot be published."
            )
