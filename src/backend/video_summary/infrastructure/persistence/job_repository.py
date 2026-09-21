"""Durable MySQL job ownership, progress and cancellation."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.video_summary.infrastructure.persistence.control_plane_repository import (
    ControlPlaneConflictError,
    SqlControlPlaneRepository,
    SubmittedJob,
)
from backend.core.ids import new_ulid
from backend.core.quota import QuotaGuard, QuotaReservation, UsageEstimate, UsageMeter, UsageRecord
from backend.core.context import WorkspaceContext
from backend.core.request_context import get_workspace_context
from backend.video_summary.infrastructure.persistence.models import Job, JobAttempt, JobEvent


class JobLeaseLostError(RuntimeError):
    """The worker no longer owns the job lease."""


@dataclass(frozen=True)
class JobSnapshot:
    id: str
    workspace_id: str
    parent_job_id: str | None
    resource_type: str
    resource_id: str
    operation: str
    status: str
    attempt_count: int
    max_attempts: int
    cancel_requested: bool
    failure_code: str | None
    failure_detail: str | None
    result_content_version: int | None


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    workspace_id: str
    resource_type: str
    resource_id: str
    operation: str
    request_payload: dict[str, Any]
    attempt_no: int
    worker_id: str
    lease_token: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class JobEventSnapshot:
    sequence: int
    status: str
    stage: str
    progress: float | None
    detail: str | None
    occurred_at: datetime


class SqlJobRepository:
    """MySQL-backed job protocol used by both local and cloud worker hosts."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        quota_guard: QuotaGuard | None = None,
        usage_meter: UsageMeter | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._control = SqlControlPlaneRepository(session_factory)
        self._quota_guard = quota_guard
        self._usage_meter = usage_meter

    def submit(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
        operation: str,
        request_payload: dict[str, Any],
        active_key: str,
        idempotency_scope_id: str | None,
        idempotency_key: str | None,
        parent_job_id: str | None = None,
    ) -> SubmittedJob:
        context = get_workspace_context()
        reservation: QuotaReservation | None = None
        payload = dict(request_payload)
        if context is not None:
            if context.workspace_id != workspace_id:
                raise ValueError("request WorkspaceContext does not own the submitted Job.")
            if self._quota_guard is not None and parent_job_id is None:
                reservation = self._quota_guard.reserve_job(
                    context,
                    operation,
                    UsageEstimate(units=1),
                    idempotency_key or active_key,
                )
                payload["_quota_reservation"] = {
                    "id": reservation.id,
                    "workspace_id": context.workspace_id,
                    "actor_id": context.actor_id,
                    "request_id": context.request_id,
                }
        try:
            submitted = self._control.submit_job(
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                operation=operation,
                request_payload=payload,
                active_key=active_key,
                idempotency_scope_id=idempotency_scope_id,
                idempotency_key=idempotency_key,
                parent_job_id=parent_job_id,
            )
        except Exception:
            self._release_reservation(reservation, "job submission failed")
            raise
        if not submitted.created:
            self._release_reservation(reservation, "existing job reused")
        return submitted

    def claim(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        operations: frozenset[str] | None = None,
    ) -> ClaimedJob | None:
        if not worker_id.strip() or lease_seconds < 1:
            raise ValueError("worker_id and a positive lease_seconds are required.")
        if operations is not None and not operations:
            raise ValueError("operations must be non-empty when supplied.")
        with self._session_factory.begin() as session:
            now = _database_now(session)
            self._recover_expired_leases(session, now)
            statement = select(Job).where(
                Job.status.in_(("queued", "retrying")),
                Job.available_at <= now,
                Job.cancel_requested_at.is_(None),
            )
            if operations is not None:
                statement = statement.where(Job.operation.in_(operations))
            job = session.scalar(
                statement
                .order_by(Job.available_at, Job.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            token = secrets.token_urlsafe(32)
            lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.status = "running"
            job.attempt_count += 1
            job.claimed_by = worker_id
            job.lease_token = token
            job.lease_expires_at = lease_expires_at
            job.started_at = job.started_at or now
            session.add(
                JobAttempt(
                    id=new_ulid(),
                    job_id=job.id,
                    attempt_no=job.attempt_count,
                    worker_id=worker_id,
                    lease_token=token,
                    started_at=now,
                    heartbeat_at=now,
                )
            )
            self._append_event(session, job.id, "running", "claimed", 0.0, "Worker 已领取任务")
            return ClaimedJob(
                id=job.id,
                workspace_id=job.workspace_id,
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                operation=job.operation,
                request_payload=dict(job.request_payload),
                attempt_no=job.attempt_count,
                worker_id=worker_id,
                lease_token=token,
                lease_expires_at=lease_expires_at,
            )

    def renew_lease(self, claim: ClaimedJob, *, lease_seconds: int) -> datetime:
        with self._session_factory.begin() as session:
            now = _database_now(session)
            job = self._owned_job(session, claim, now)
            expires_at = now + timedelta(seconds=lease_seconds)
            job.lease_expires_at = expires_at
            attempt = session.scalar(
                select(JobAttempt).where(
                    JobAttempt.job_id == claim.id,
                    JobAttempt.attempt_no == claim.attempt_no,
                    JobAttempt.lease_token == claim.lease_token,
                )
            )
            if attempt is None:
                raise JobLeaseLostError("Job attempt is missing.")
            attempt.heartbeat_at = now
            return expires_at

    def append_progress(
        self,
        claim: ClaimedJob,
        *,
        stage: str,
        progress: float | None,
        detail: str | None,
    ) -> None:
        with self._session_factory.begin() as session:
            now = _database_now(session)
            job = self._owned_job(session, claim, now)
            self._append_event(session, job.id, job.status, stage, progress, detail)

    def cancel_requested(self, claim: ClaimedJob) -> bool:
        with self._session_factory() as session:
            job = session.get(Job, claim.id)
            if job is None:
                raise JobLeaseLostError("Job no longer exists.")
            if job.claimed_by != claim.worker_id or job.lease_token != claim.lease_token:
                raise JobLeaseLostError("Job lease was replaced.")
            return job.cancel_requested_at is not None or job.status in {"cancelling", "cancelled"}

    def request_cancel(self, job_id: str, *, workspace_id: str | None = None) -> JobSnapshot | None:
        with self._session_factory.begin() as session:
            now = _database_now(session)
            statement = select(Job).where(Job.id == job_id)
            if workspace_id is not None:
                statement = statement.where(Job.workspace_id == workspace_id)
            job = session.scalar(statement.with_for_update())
            if job is None:
                return None
            snapshot = self._request_cancel_locked(session, job, now)
        self.finalize_accounting(job_id, workspace_id=workspace_id)
        return snapshot

    def finalize_accounting(self, job_id: str, *, workspace_id: str) -> None:
        """Settle or release the reservation recorded with a terminal Job once."""

        action: tuple[str, QuotaReservation, WorkspaceContext] | None = None
        with self._session_factory.begin() as session:
            statement = select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id)
            job = session.scalar(statement.with_for_update())
            if job is None or job.status not in {"succeeded", "failed", "cancelled"}:
                return
            payload = dict(job.request_payload)
            reservation_payload = payload.get("_quota_reservation")
            if not isinstance(reservation_payload, dict) or reservation_payload.get("finalized") is True:
                return
            reservation_id = reservation_payload.get("id")
            context = _context_from_reservation(reservation_payload)
            if not isinstance(reservation_id, str) or context is None:
                return
            reservation_payload["finalized"] = True
            payload["_quota_reservation"] = reservation_payload
            job.request_payload = payload
            action = (job.status, QuotaReservation(reservation_id), context)
        if action is None or self._quota_guard is None:
            return
        status, reservation, context = action
        if status == "succeeded":
            self._quota_guard.settle(reservation.id, UsageRecord(units=1))
            if self._usage_meter is not None:
                self._usage_meter.record(context, UsageRecord(units=1))
        else:
            self._quota_guard.release(reservation.id, f"job {status}")

    def request_cancel_for_resource(self, *, workspace_id: str, resource_id: str, operation: str) -> JobSnapshot | None:
        with self._session_factory() as session:
            job_id = session.scalar(
                select(Job.id)
                .where(Job.workspace_id == workspace_id, Job.resource_id == resource_id, Job.operation == operation, Job.status.in_(("queued", "retrying", "running", "cancelling")))
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        return self.request_cancel(job_id, workspace_id=workspace_id) if job_id is not None else None

    def request_cancel_series_generation(self, *, workspace_id: str, series_id: str) -> list[JobSnapshot]:
        """Cancel an active series batch and every generation child it owns."""

        active_statuses = ("queued", "retrying", "running", "cancelling")
        with self._session_factory.begin() as session:
            parent = session.scalar(
                select(Job)
                .where(
                    Job.workspace_id == workspace_id,
                    Job.resource_id == series_id,
                    Job.operation == "generate_series_batch",
                )
                .order_by(Job.created_at.desc())
                .with_for_update()
                .limit(1)
            )
            if parent is None:
                return []
            jobs = list(
                session.scalars(
                    select(Job)
                    .where(
                        Job.workspace_id == workspace_id,
                        Job.status.in_(active_statuses),
                        (Job.id == parent.id) | (Job.parent_job_id == parent.id),
                    )
                    .with_for_update()
                )
            )
            now = _database_now(session)
            return [self._request_cancel_locked(session, job, now) for job in jobs]

    def mark_cancelled(self, claim: ClaimedJob, *, detail: str) -> None:
        with self._session_factory.begin() as session:
            now = _database_now(session)
            job = self._owned_job(session, claim, now, allow_cancelling=True)
            job.status = "cancelled"
            job.active_key = None
            job.finished_at = now
            job.lease_expires_at = None
            self._finish_attempt(session, claim, now, outcome="cancelled")
            self._append_event(session, job.id, "cancelled", "cancelled", None, detail)

    def succeed(self, claim: ClaimedJob, *, detail: str) -> None:
        """Finish a worker-owned Job whose handler committed its own result."""

        with self._session_factory.begin() as session:
            now = _database_now(session)
            job = self._owned_job(session, claim, now, allow_cancelling=True)
            if job.cancel_requested_at is not None:
                job.status = "cancelled"
                job.active_key = None
                job.claimed_by = None
                job.lease_token = None
                job.lease_expires_at = None
                job.finished_at = now
                self._finish_attempt(session, claim, now, outcome="cancelled")
                self._append_event(session, job.id, "cancelled", "cancelled", None, "任务已取消")
                return
            job.status = "succeeded"
            job.active_key = None
            job.claimed_by = None
            job.lease_token = None
            job.lease_expires_at = None
            job.finished_at = now
            self._finish_attempt(session, claim, now, outcome="succeeded")
            self._append_event(session, job.id, "succeeded", "succeeded", 100.0, detail)

    def fail(self, claim: ClaimedJob, *, failure_code: str, failure_detail: str, retry_delay_seconds: int | None) -> None:
        with self._session_factory.begin() as session:
            now = _database_now(session)
            job = self._owned_job(session, claim, now, allow_cancelling=True)
            if job.cancel_requested_at is not None:
                job.status = "cancelled"
                job.active_key = None
                job.finished_at = now
                self._finish_attempt(session, claim, now, outcome="cancelled")
                self._append_event(session, job.id, "cancelled", "cancelled", None, "任务已取消")
                return
            job.failure_code = failure_code
            job.failure_detail = failure_detail
            job.lease_expires_at = None
            self._finish_attempt(session, claim, now, outcome="failed", failure_code=failure_code, failure_detail=failure_detail)
            if retry_delay_seconds is not None and job.attempt_count < job.max_attempts:
                job.status = "retrying"
                job.claimed_by = None
                job.lease_token = None
                job.available_at = now + timedelta(seconds=retry_delay_seconds)
                self._append_event(session, job.id, "retrying", "retrying", None, "任务将在稍后重试")
            else:
                job.status = "failed"
                job.active_key = None
                job.finished_at = now
                self._append_event(session, job.id, "failed", "failed", None, failure_detail)

    def get(self, job_id: str, *, workspace_id: str | None = None) -> JobSnapshot | None:
        with self._session_factory() as session:
            statement = select(Job).where(Job.id == job_id)
            if workspace_id is not None:
                statement = statement.where(Job.workspace_id == workspace_id)
            job = session.scalar(statement)
            return _snapshot(job) if job is not None else None

    def latest_for_resource(self, *, workspace_id: str, resource_id: str, operations: tuple[str, ...]) -> JobSnapshot | None:
        if not workspace_id or not resource_id or not operations:
            raise ValueError("workspace_id, resource_id and operations are required.")
        with self._session_factory() as session:
            job = session.scalar(
                select(Job)
                .where(Job.workspace_id == workspace_id, Job.resource_id == resource_id, Job.operation.in_(operations))
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            return _snapshot(job) if job is not None else None

    def active_for_resource(self, *, workspace_id: str, resource_id: str, operation: str) -> JobSnapshot | None:
        with self._session_factory() as session:
            job = session.scalar(
                select(Job)
                .where(
                    Job.workspace_id == workspace_id,
                    Job.resource_id == resource_id,
                    Job.operation == operation,
                    Job.status.in_(("queued", "retrying", "running", "cancelling")),
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            return _snapshot(job) if job is not None else None

    def _request_cancel_locked(self, session: Session, job: Job, now: datetime) -> JobSnapshot:
        if job.status in {"succeeded", "failed", "cancelled"}:
            return _snapshot(job)
        job.cancel_requested_at = now
        if job.status in {"queued", "retrying"}:
            job.status = "cancelled"
            job.active_key = None
            job.finished_at = now
            self._append_event(session, job.id, "cancelled", "cancelled", None, "任务在执行前被取消")
        else:
            job.status = "cancelling"
            self._append_event(session, job.id, "cancelling", "cancelling", None, "已请求取消任务")
        return _snapshot(job)

    def _release_reservation(self, reservation: QuotaReservation | None, reason: str) -> None:
        if reservation is not None and self._quota_guard is not None:
            self._quota_guard.release(reservation.id, reason)

    def latest_event(self, job_id: str, *, workspace_id: str) -> JobEventSnapshot | None:
        with self._session_factory() as session:
            job = session.scalar(select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id))
            event = session.scalar(
                select(JobEvent)
                .where(JobEvent.job_id == job_id)
                .order_by(JobEvent.sequence.desc())
                .limit(1)
            )
        if job is None or event is None:
            return None
        return JobEventSnapshot(
            sequence=event.sequence,
            status=job.status,
            stage=event.stage,
            progress=event.progress,
            detail=event.detail,
            occurred_at=event.created_at,
        )

    def events(self, job_id: str, *, after_sequence: int, workspace_id: str | None = None) -> list[JobEventSnapshot]:
        with self._session_factory() as session:
            job_statement = select(Job).where(Job.id == job_id)
            if workspace_id is not None:
                job_statement = job_statement.where(Job.workspace_id == workspace_id)
            status = session.scalar(job_statement)
            if status is None:
                return []
            rows = session.scalars(
                select(JobEvent)
                .where(JobEvent.job_id == job_id, JobEvent.sequence > after_sequence)
                .order_by(JobEvent.sequence)
            ).all()
        current_status = status.status if status is not None else "missing"
        return [
            JobEventSnapshot(
                sequence=row.sequence,
                status=current_status,
                stage=row.stage,
                progress=row.progress,
                detail=row.detail,
                occurred_at=row.created_at,
            )
            for row in rows
        ]

    def _recover_expired_leases(self, session: Session, now: datetime) -> None:
        expired = session.scalars(
            select(Job)
            .where(Job.status.in_(("running", "cancelling")), Job.lease_expires_at.is_not(None), Job.lease_expires_at < now)
            .with_for_update(skip_locked=True)
        ).all()
        for job in expired:
            attempt = session.scalar(
                select(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.attempt_no == job.attempt_count)
            )
            if attempt is not None and attempt.finished_at is None:
                attempt.finished_at = now
                attempt.outcome = "lost_lease"
                attempt.failure_code = "lease_lost"
                attempt.failure_detail = "Worker lease expired."
            job.claimed_by = None
            job.lease_token = None
            job.lease_expires_at = None
            if job.cancel_requested_at is not None:
                job.status = "cancelled"
                job.active_key = None
                job.finished_at = now
                self._append_event(session, job.id, "cancelled", "cancelled", None, "Worker lease 过期后确认取消")
            elif job.attempt_count < job.max_attempts:
                job.status = "retrying"
                job.available_at = now
                self._append_event(session, job.id, "retrying", "lease_recovered", None, "Worker lease 已过期，任务将重试")
            else:
                job.status = "failed"
                job.active_key = None
                job.finished_at = now
                job.failure_code = "lease_lost"
                job.failure_detail = "Worker lease expired and retry budget is exhausted."
                self._append_event(session, job.id, "failed", "lease_lost", None, job.failure_detail)

    @staticmethod
    def _append_event(
        session: Session,
        job_id: str,
        status: str,
        stage: str,
        progress: float | None,
        detail: str | None,
    ) -> None:
        del status
        sequence = (session.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id)) or 0) + 1
        session.add(JobEvent(id=new_ulid(), job_id=job_id, sequence=sequence, stage=stage, progress=progress, detail=detail))

    @staticmethod
    def _owned_job(session: Session, claim: ClaimedJob, now: datetime, *, allow_cancelling: bool = False) -> Job:
        statuses = ("running", "cancelling") if allow_cancelling else ("running",)
        job = session.scalar(
            select(Job)
            .where(
                Job.id == claim.id,
                Job.status.in_(statuses),
                Job.claimed_by == claim.worker_id,
                Job.lease_token == claim.lease_token,
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at > now,
            )
            .with_for_update()
        )
        if job is None:
            raise JobLeaseLostError("Job lease is no longer valid.")
        return job

    @staticmethod
    def _finish_attempt(
        session: Session,
        claim: ClaimedJob,
        now: datetime,
        *,
        outcome: str,
        failure_code: str | None = None,
        failure_detail: str | None = None,
    ) -> None:
        attempt = session.scalar(
            select(JobAttempt).where(
                JobAttempt.job_id == claim.id,
                JobAttempt.attempt_no == claim.attempt_no,
                JobAttempt.lease_token == claim.lease_token,
            )
        )
        if attempt is None:
            raise JobLeaseLostError("Job attempt is missing.")
        attempt.finished_at = now
        attempt.outcome = outcome
        attempt.failure_code = failure_code
        attempt.failure_detail = failure_detail


def _snapshot(job: Job) -> JobSnapshot:
    return JobSnapshot(
        id=job.id,
        workspace_id=job.workspace_id,
        parent_job_id=job.parent_job_id,
        resource_type=job.resource_type,
        resource_id=job.resource_id,
        operation=job.operation,
        status=job.status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested_at is not None,
        failure_code=job.failure_code,
        failure_detail=job.failure_detail,
        result_content_version=job.result_content_version,
    )


def _database_now(session: Session) -> datetime:
    """Use the database clock for every value compared with MySQL DATETIME."""

    return session.scalar(select(func.now()))


def _context_from_reservation(payload: dict[str, object]) -> WorkspaceContext | None:
    workspace_id, actor_id, request_id = payload.get("workspace_id"), payload.get("actor_id"), payload.get("request_id")
    if not all(isinstance(value, str) and value.strip() for value in (workspace_id, actor_id, request_id)):
        return None
    return WorkspaceContext(workspace_id=workspace_id, actor_id=actor_id, request_id=request_id)
