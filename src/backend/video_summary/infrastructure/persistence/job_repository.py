"""Durable MySQL job ownership, progress and cancellation."""

from __future__ import annotations
from contextlib import nullcontext

import secrets
import hashlib
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.video_summary.infrastructure.persistence.control_plane_repository import (
    SqlControlPlaneRepository,
    SubmittedJob,
)
from backend.core.ids import new_ulid
from backend.core.quota import QuotaGuard, QuotaReservation, UsageEstimate, UsageMeter, UsageRecord
from backend.core.context import WorkspaceContext
from backend.core.request_context import get_workspace_context
from backend.video_summary.infrastructure.persistence.models import Job, JobAttempt, JobEvent, Workspace, Video, Series, VideoContentState, IdempotencyKey
from backend.core.preferences import current_preferences
from backend.shared.llm.usage import MySqlLlmUsageStore
from backend.video_summary.infrastructure.persistence.execution_context import JobLeaseLostError


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
    started_at: datetime | None
    finished_at: datetime | None
    actor_id: str | None = None
    created_at: datetime | None = None
    accounting_status: str = "none"


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
    started_at: datetime | None


class SqlJobRepository:
    """MySQL-backed job protocol used by both local and cloud worker hosts."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        quota_guard: QuotaGuard | None = None,
        usage_meter: UsageMeter | None = None,
        token_estimate=None,
        multimodal_estimate=None,
        queue_policy=None,
    ) -> None:
        self._session_factory = session_factory
        self._control = SqlControlPlaneRepository(session_factory)
        self._quota_guard = quota_guard
        self._usage_meter = usage_meter
        self._token_estimate = token_estimate
        self._multimodal_estimate = multimodal_estimate
        self._queue_policy = queue_policy

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
        prepaid_reservation: QuotaReservation | None = None,
    ) -> SubmittedJob:
        context = get_workspace_context()
        reservation = prepaid_reservation
        payload = dict(request_payload)
        operation_id = new_ulid()
        for internal in ("_quota_reservation", "_execution_context", "_user_preferences", "_usage_estimate"):
            payload.pop(internal, None)
        if context is not None:
            payload["_execution_context"] = {"actor_id": context.actor_id, "request_id": context.request_id}
            if context.workspace_id != workspace_id:
                raise ValueError("request WorkspaceContext does not own the submitted Job.")
            preferences = current_preferences()
            if preferences is not None:
                payload["_user_preferences"] = preferences
            if idempotency_scope_id is not None:
                idempotency_scope_id = hashlib.sha256((idempotency_scope_id + ":" + context.actor_id).encode()).hexdigest()
                with self._session_factory.begin() as session:
                    from backend.video_summary.infrastructure.persistence.control_plane_repository import _request_hash
                    existing = self._control._find_idempotent_job(session, scope_id=idempotency_scope_id, key=idempotency_key, request_hash=_request_hash(payload))
                    if existing is not None:
                        return existing
            active = self.active_for_resource(workspace_id=workspace_id, resource_id=resource_id, operation=operation)
            if active is not None:
                return SubmittedJob(id=active.id, created=False, status=active.status)
            estimate = self.estimate_usage(
                context,
                resource_type,
                resource_id,
                operation_id,
                processing_mode=payload.get("processing_mode"),
                video_ids=payload.get('video_ids'),
            )
            if payload.get("manual_transcript") is not None:
                from dataclasses import replace
                estimate = replace(estimate, transcript_available=True)
            payload["_usage_estimate"] = asdict(estimate)
            if self._quota_guard is not None and parent_job_id is None:
                if reservation is None:
                    reservation = self._quota_guard.reserve_job(context,operation,estimate,idempotency_key or estimate.operation_id)
                payload["_quota_reservation"] = {
                    "id": reservation.id,
                    "workspace_id": context.workspace_id,
                    "actor_id": context.actor_id,
                    "request_id": context.request_id,
                }
        try:
            admission = self._queue_policy.admit(
                actor_id=context.actor_id,
                units=max(1, estimate.units) if operation == "generate_series_batch" else 1,
            ) if self._queue_policy is not None and context is not None and parent_job_id is None and resource_type in {"video", "series"} else nullcontext()
            with admission:
                submitted = self._control.submit_job(
                    job_id=operation_id,
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

    def request_index_refresh(self, workspace_id: str) -> None:
        with self._session_factory.begin() as session:
            workspace = session.scalar(select(Workspace).where(Workspace.id == workspace_id,
                Workspace.deleted_at.is_(None)).with_for_update())
            if workspace is None:
                raise LookupError("workspace not found")
            workspace.index_revision_requested += 1
            self._ensure_index_job(session, workspace_id)

    @staticmethod
    def _ensure_index_job(session, workspace_id: str) -> None:
        key = f"workspace:{workspace_id}:refresh_rag_index"
        active = session.scalar(select(Job.id).where(Job.active_key == key))
        if active is not None:
            return
        job_id = new_ulid()
        session.add(Job(id=job_id, workspace_id=workspace_id, resource_type="workspace",
            resource_id=workspace_id, operation="refresh_rag_index", status="queued",
            request_payload={"workspace_id": workspace_id}, active_key=key))
        session.flush()
        session.add(JobEvent(id=new_ulid(), job_id=job_id, sequence=1, stage="queued", progress=0.0))

    def index_generation(self, workspace_id: str) -> str | None:
        with self._session_factory() as session:
            return session.scalar(select(Workspace.index_generation).where(Workspace.id == workspace_id))

    def index_refresh_revision(self, workspace_id: str) -> int:
        with self._session_factory() as session:
            value = session.scalar(select(Workspace.index_revision_requested).where(Workspace.id == workspace_id))
            if value is None:
                raise LookupError("workspace not found")
            return value

    def complete_index_refresh(self, claim: ClaimedJob, revision: int, generation: str) -> None:
        with self._session_factory.begin() as session:
            self._owned_job(session, claim, _database_now(session))
            workspace = session.scalar(select(Workspace).where(Workspace.id == claim.workspace_id).with_for_update())
            workspace.index_generation = generation
            workspace.index_revision_completed = max(workspace.index_revision_completed, revision)

    def children(self, job_id: str, *, workspace_id: str) -> list[JobSnapshot]:
        with self._session_factory() as session:
            jobs = session.scalars(select(Job).where(Job.parent_job_id == job_id,
                Job.workspace_id == workspace_id).order_by(Job.created_at, Job.id)).all()
            return [_snapshot(job) for job in jobs]

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
        with (self._queue_policy.lock() if self._queue_policy is not None else nullcontext()), self._session_factory.begin() as session:
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
                .order_by(*(self._queue_policy.scheduling_order() if self._queue_policy is not None else (Job.available_at, Job.created_at)))
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
            self._append_event(session, job.id, "running", "claimed", 0.0, "正在准备任务")
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
        allow_cancelling: bool = False,
    ) -> None:
        with self._session_factory.begin() as session:
            now = _database_now(session)
            job = self._owned_job(session, claim, now, allow_cancelling=allow_cancelling)
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
            if job.operation == "generate_series_batch":
                children = session.scalars(select(Job).where(Job.parent_job_id == job.id,
                    Job.workspace_id == job.workspace_id).with_for_update()).all()
                for child in children:
                    self._request_cancel_locked(session, child, now)
            snapshot = self._request_cancel_locked(session, job, now)
        self.finalize_accounting(job_id, workspace_id=workspace_id)
        return snapshot

    def estimate_usage(self, context, resource_type, resource_id, operation_id, *, processing_mode=None, video_ids=None):
        if processing_mode not in {None, "summary", "transcript"}:
            raise ValueError("Unsupported processing mode.")
        with self._session_factory() as session:
            query = select(
                Video.id,
                Video.duration_ms,
                Video.content_version,
                VideoContentState.transcript_version,
            ).join(Series, Video.series_id == Series.id).outerjoin(
                VideoContentState, VideoContentState.video_id == Video.id,
            ).where(Series.workspace_id == context.workspace_id, Video.deleted_at.is_(None))
            if resource_type == "video":
                rows = session.execute(query.where(Video.id == resource_id)).all()
            elif resource_type == "series":
                if video_ids is not None:
                    if not video_ids:raise ValueError('At least one video must be selected.')
                    query=query.where(Video.id.in_(video_ids))
                pending = (
                    (VideoContentState.transcript_version.is_(None))
                    | (VideoContentState.transcript_version < Video.content_version)
                    if processing_mode == "transcript"
                    else Video.content_version == 0
                )
                rows = session.execute(query.where(Series.id == resource_id, pending)).all()
            else:
                rows = []
        incoming, outgoing = self._token_estimate() if self._token_estimate is not None else (None, None)
        profile = (current_preferences() or {}).get("model_profile")
        multimodal = processing_mode != 'transcript' and (
            self._multimodal_estimate() if self._multimodal_estimate is not None else
            bool((current_preferences() or {}).get('ai_summary_multimodal_enabled')))
        child_operation = "generate_transcript" if processing_mode == "transcript" else "generate_summary"
        estimates = tuple(
            UsageEstimate(
                units=1,
                operation_id=f"{operation_id}:{row.id}",
                operation=child_operation,
                model_profile=profile,
                multimodal_enabled=multimodal,
                duration_seconds=(row.duration_ms / 1000 if row.duration_ms is not None else None),
                input_tokens=incoming,
                output_tokens=outgoing,
                transcript_available=row.transcript_version is not None and row.transcript_version > 0,
            )
            for row in rows
        )
        if resource_type == "series":
            return UsageEstimate(
                units=len(estimates), operation_id=operation_id, operation="generate_series_batch",
                model_profile=profile, children=estimates,
            )
        return estimates[0] if estimates else UsageEstimate(units=0, operation_id=operation_id, model_profile=profile)

    def admission(self, context, units):
        return self._queue_policy.admit(actor_id=context.actor_id,units=units) if self._queue_policy is not None else nullcontext()

    def in_transaction(self, sessions):
        """Reuse metering dependencies while the caller owns queue admission and SQL commit."""
        return SqlJobRepository(sessions,quota_guard=self._quota_guard,usage_meter=self._usage_meter,
            token_estimate=self._token_estimate,multimodal_estimate=self._multimodal_estimate)

    def submission_for_key(self, context, key):
        scope=hashlib.sha256((context.workspace_id+':'+context.actor_id).encode()).hexdigest()
        with self._session_factory() as session:
            job=session.scalar(select(Job).join(IdempotencyKey,IdempotencyKey.job_id==Job.id).where(
                IdempotencyKey.scope_id==scope,IdempotencyKey.key==key,
                Job.workspace_id==context.workspace_id,Job.actor_id==context.actor_id))
            if job is None:return None
            from backend.core.jobs import job_snapshot_payload
            return {**job_snapshot_payload(_snapshot(job)), 'video_ids':job.request_payload.get('video_ids',[])}

    def measured_usage(self, session, job):
        children = session.scalars(select(Job).where(Job.parent_job_id == job.id)).all() if job.operation == "generate_series_batch" else []
        completed = [item for item in children if item.status == "succeeded" or item.result_content_version is not None] if job.operation == "generate_series_batch" else ([job] if job.status == "succeeded" or job.result_content_version is not None else [])
        operation_ids = [job.id, *(item.id for item in children)]
        totals = MySqlLlmUsageStore(self._session_factory).summarize(range_key="all", workspace_id=job.workspace_id, actor_id=job.actor_id, operation_ids=operation_ids).total
        video_ids = [item.resource_id for item in completed if item.resource_type == "video"]
        durations = session.scalars(select(Video.duration_ms).where(Video.id.in_(video_ids))).all() if video_ids else []
        seconds = sum(durations) / 1000 if durations and all(value is not None for value in durations) else None
        preferences = job.request_payload.get("_user_preferences", {})
        return UsageRecord(units=len(completed), operation_id=job.id, operation=job.operation,
                           model_profile=preferences.get("model_profile"), duration_seconds=seconds,
                           input_tokens=totals.prompt_tokens, output_tokens=totals.completion_tokens,
                           transcript_available=job.request_payload.get("_usage_estimate", {}).get("transcript_available"),
                           multimodal_enabled=job.request_payload.get("_usage_estimate", {}).get("multimodal_enabled", False),
                           children=tuple(self.measured_usage(session, child) for child in completed) if children else ())

    def mark_series_batch_waiting(self, claim, *, child_count: int) -> None:
        if child_count < 1:
            raise ValueError("A waiting series batch requires at least one child.")
        with self._session_factory.begin() as session:
            now = _database_now(session)
            job = self._owned_job(session, claim, now)
            job.status = "waiting_children"
            job.claimed_by = None
            job.lease_token = None
            job.lease_expires_at = None
            self._finish_attempt(session, claim, now, outcome="dispatched")
            self._append_event(
                session, job.id, "waiting_children", "waiting_children", 0.0,
                f"已创建 {child_count} 个视频子任务，等待全部结束",
            )

    def reconcile_series_batches(self, limit=20) -> list[tuple[str, str]]:
        terminal = {"succeeded", "failed", "cancelled"}
        child = Job.__table__.alias("batch_child")
        finalized: list[tuple[str, str]] = []
        with self._session_factory.begin() as session:
            parents = session.scalars(
                select(Job).where(
                    Job.operation == "generate_series_batch",
                    Job.status.in_(("waiting_children", "cancelling")),
                    Job.lease_token.is_(None),
                    select(child.c.id).where(child.c.parent_job_id == Job.id).exists(),
                    ~select(child.c.id).where(child.c.parent_job_id == Job.id,
                        child.c.status.not_in(terminal)).exists(),
                ).order_by(Job.created_at).limit(limit).with_for_update(skip_locked=True)
            ).all()
            now = _database_now(session)
            for parent in parents:
                children = session.scalars(
                    select(Job).where(Job.parent_job_id == parent.id).with_for_update()
                ).all()
                if not children:
                    continue
                if any(child.status not in terminal for child in children):
                    continue
                if parent.cancel_requested_at is not None or any(child.status == "cancelled" for child in children):
                    status, detail = "cancelled", "系列任务已取消"
                elif any(child.status == "failed" for child in children):
                    status, detail = "failed", "系列任务中存在失败的视频"
                    parent.failure_code = "child_generation_failed"
                    parent.failure_detail = detail
                else:
                    status, detail = "succeeded", "系列全部视频处理完成"
                parent.status = status
                parent.active_key = None
                parent.claimed_by = None
                parent.lease_token = None
                parent.lease_expires_at = None
                parent.finished_at = now
                self._append_event(session, parent.id, status, status, 100.0, detail)
                finalized.append((parent.id, parent.workspace_id))
        return finalized

    def finalize_accounting(self, job_id: str, *, workspace_id: str) -> None:
        """Finalize after host success. Host settlement and metering must be idempotent."""
        if self._quota_guard is None:
            return
        with self._session_factory.begin() as session:
            job = session.scalar(select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id).with_for_update())
            if job is None or job.status not in {"succeeded", "failed", "cancelled"}:
                return
            payload = dict(job.request_payload)
            reservation = dict(payload.get("_quota_reservation", {}))
            if not reservation or reservation.get("finalized") is True:
                return
            context = _context_from_reservation(reservation)
            if not reservation.get("id") or context is None:
                raise ValueError("Invalid accounting ownership metadata.")
            if job.operation == "generate_series_batch":
                children = session.scalars(select(Job).where(Job.parent_job_id == job.id)).all()
                if any(child.status not in {"succeeded", "failed", "cancelled"} for child in children):
                    return
            actual = self.measured_usage(session, job)
            if actual.units:
                self._quota_guard.settle(reservation["id"], actual)
                if self._usage_meter is not None:
                    self._usage_meter.record(context, actual)
            else:
                self._quota_guard.release(reservation["id"], f"job {job.status}")
            reservation["finalized"] = True
            payload["_quota_reservation"] = reservation
            job.request_payload = payload
            job.accounting_status = "settled"

    def retry_accounting(self, limit=20):
        with self._session_factory() as session:
            rows = session.execute(select(Job.id, Job.workspace_id).where(Job.accounting_status == "pending", Job.status.in_(("succeeded", "failed", "cancelled"))).order_by(Job.finished_at).limit(limit)).all()
        for job_id, workspace_id in rows:
            try:
                self.finalize_accounting(job_id, workspace_id=workspace_id)
            except Exception:
                logging.getLogger(__name__).exception("Job accounting remains pending", extra={"job_id": job_id})

    def list_jobs(self, *, workspace_id=None, actor_id=None, status=None, operation=None, offset=0, limit=50, user_tasks=True):
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid task pagination.")
        query = self._jobs_query(workspace_id, actor_id, status, operation, user_tasks)
        with self._session_factory() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(query.order_by(Job.created_at.desc(), Job.id.desc()).offset(offset).limit(limit)).all()
            return {"total": total, "items": [_snapshot(row) for row in rows]}

    def job_statistics(self, *, workspace_id=None, actor_id=None, user_tasks=True):
        query = self._jobs_query(workspace_id, actor_id, None, None, user_tasks).subquery()
        with self._session_factory() as session:
            return dict(session.execute(select(query.c.status, func.count()).group_by(query.c.status)).all())

    @staticmethod
    def _jobs_query(workspace_id, actor_id, status, operation, user_tasks):
        query = select(Job)
        if workspace_id is not None:
            query = query.where(Job.workspace_id == workspace_id)
        if actor_id is not None:
            query = query.where(Job.actor_id == actor_id)
        if status is not None:
            if status not in {"queued", "running", "retrying", "cancelling", "succeeded", "failed", "cancelled"}:
                raise ValueError("Unsupported task status.")
            query = query.where(Job.status == status)
        if operation is not None:
            query = query.where(Job.operation == operation)
        if user_tasks:
            query = query.where(Job.actor_id.is_not(None), Job.resource_type.in_(("video", "series")), Job.operation != "generate_series_batch")
        return query

    def request_cancel_for_resource(self, *, workspace_id: str, resource_id: str, operation: str) -> JobSnapshot | None:
        with self._session_factory() as session:
            job_id = session.scalar(
                select(Job.id)
                .where(Job.workspace_id == workspace_id, Job.resource_id == resource_id, Job.operation == operation, Job.status.in_(("queued", "retrying", "running", "cancelling")))
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        return self.request_cancel(job_id, workspace_id=workspace_id) if job_id is not None else None

    def request_cancel_series_generation(self, *, workspace_id: str, series_id: str, run_id: str | None = None) -> list[JobSnapshot]:
        """Cancel an active series batch and every generation child it owns."""

        active_statuses = ("queued", "retrying", "running", "cancelling", "waiting_children")
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
            parent_run_id = parent.request_payload.get("run_id")
            if run_id is not None and parent_run_id != run_id:
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
            terminal = {"succeeded", "failed", "cancelled"}
            if parent.status in terminal and any(job.id != parent.id for job in jobs):
                parent.active_key = f"series:{parent.resource_id}:generate_series_batch"
                parent.finished_at = None
                parent.failure_code = None
                parent.failure_detail = None
                parent.cancel_requested_at = now
                parent.status = "cancelling"
                self._append_event(session, parent.id, "cancelling", "cancelling", None, "已请求取消系列任务")
            elif parent.status == "waiting_children":
                parent.cancel_requested_at = now
                parent.status = "cancelling"
                self._append_event(session, parent.id, "cancelling", "cancelling", None, "已请求取消系列任务")
            elif parent.status in active_statuses:
                self._request_cancel_locked(session, parent, now)
            snapshots = [
                self._request_cancel_locked(session, job, now)
                for job in jobs
                if job.id != parent.id
            ]
            return [_snapshot(parent), *snapshots]

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

    def succeed(self, claim: ClaimedJob, *, detail: str) -> bool:
        """Atomically finish a worker-owned Job, unless its handler already finished it."""

        with self._session_factory.begin() as session:
            now = _database_now(session)
            current = session.scalar(select(Job).where(Job.id == claim.id).with_for_update())
            if current is None:
                raise JobLeaseLostError("Job no longer exists.")
            if current.status in {"succeeded", "cancelled"}:
                return False
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
                return True
            job.status = "succeeded"
            job.active_key = None
            job.claimed_by = None
            job.lease_token = None
            job.lease_expires_at = None
            job.finished_at = now
            self._finish_attempt(session, claim, now, outcome="succeeded")
            self._append_event(session, job.id, "succeeded", "succeeded", 100.0, detail)
            if claim.operation == "refresh_rag_index":
                workspace = session.scalar(select(Workspace).where(Workspace.id == claim.workspace_id).with_for_update())
                if workspace.index_revision_requested > workspace.index_revision_completed:
                    session.flush()
                    self._ensure_index_job(session, claim.workspace_id)
            return True

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
                    Job.status.in_(("queued", "retrying", "running", "cancelling", "waiting_children")),
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
            started_at=job.started_at,
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
        return [
            JobEventSnapshot(
                sequence=row.sequence,
                # 重放历史步骤时不能把它们都标成当前终态，否则客户端会在
                # 第一条旧事件处关闭连接，丢失后面的真实步骤和完成事件。
                status=(row.stage if row.stage in {"queued", "retrying", "cancelling", "succeeded", "failed", "cancelled"} else "running"),
                stage=row.stage,
                progress=row.progress,
                detail=row.detail,
                occurred_at=row.created_at,
                started_at=status.started_at,
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
        started_at=job.started_at,
        finished_at=job.finished_at,
        actor_id=job.actor_id, created_at=job.created_at, accounting_status=job.accounting_status,
    )


def _database_now(session: Session) -> datetime:
    """Use the database clock for every value compared with MySQL DATETIME."""

    return session.scalar(select(func.now()))


def _context_from_reservation(payload: dict[str, object]) -> WorkspaceContext | None:
    workspace_id, actor_id, request_id = payload.get("workspace_id"), payload.get("actor_id"), payload.get("request_id")
    if not all(isinstance(value, str) and value.strip() for value in (workspace_id, actor_id, request_id)):
        return None
    return WorkspaceContext(workspace_id=workspace_id, actor_id=actor_id, request_id=request_id)
