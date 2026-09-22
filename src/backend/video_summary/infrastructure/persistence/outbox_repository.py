"""Durable Outbox claiming, confirmation, retry, and retention."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from backend.video_summary.infrastructure.persistence.models import OutboxEvent


@dataclass(frozen=True)
class ClaimedOutboxEvent:
    id: str
    workspace_id: str
    claim_token: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, object]
    attempt_count: int


@dataclass(frozen=True)
class OutboxRetryPolicy:
    """Bounded exponential retry policy shared by all SQL Outbox workers."""

    max_attempts: int = 5
    initial_delay_seconds: int = 5
    max_delay_seconds: int = 300

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive.")
        if self.initial_delay_seconds < 1 or self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("retry delays must be positive and max_delay_seconds must not be smaller than initial_delay_seconds.")

    def retry_delay(self, failed_attempt_count: int) -> timedelta:
        if failed_attempt_count < 1:
            raise ValueError("failed_attempt_count must be positive.")
        seconds = min(self.initial_delay_seconds * (2 ** (failed_attempt_count - 1)), self.max_delay_seconds)
        return timedelta(seconds=seconds)


class SqlOutboxRepository:
    """MySQL outbox with lease ownership, explicit confirmation, and cleanup."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def claim_batch(
        self,
        *,
        workspace_id: str,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
        limit: int = 25,
    ) -> list[ClaimedOutboxEvent]:
        if not workspace_id.strip() or not worker_id.strip() or lease_seconds < 1 or max_attempts < 1 or limit < 1:
            raise ValueError("workspace_id, worker_id, and positive lease_seconds, max_attempts, and limit are required.")
        with self._sessions.begin() as session:
            now = _database_now(session)
            expired_before = now - timedelta(seconds=lease_seconds)
            events = session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.workspace_id == workspace_id,
                    OutboxEvent.delivered_at.is_(None),
                    OutboxEvent.dead_lettered_at.is_(None),
                    OutboxEvent.attempt_count < max_attempts,
                    OutboxEvent.available_at <= now,
                    (OutboxEvent.claimed_at.is_(None) | (OutboxEvent.claimed_at < expired_before)),
                )
                .order_by(OutboxEvent.occurred_at, OutboxEvent.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            ).all()
            claimed: list[ClaimedOutboxEvent] = []
            for event in events:
                token = secrets.token_urlsafe(32)
                event.claimed_at = now
                event.claim_token = token
                claimed.append(
                    ClaimedOutboxEvent(
                        id=event.id,
                        workspace_id=event.workspace_id,
                        claim_token=token,
                        event_type=event.event_type,
                        aggregate_type=event.aggregate_type,
                        aggregate_id=event.aggregate_id,
                        payload=dict(event.payload),
                        attempt_count=event.attempt_count,
                    )
                )
            return claimed

    def confirm_delivered(self, event: ClaimedOutboxEvent) -> None:
        with self._sessions.begin() as session:
            row = session.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == event.id, OutboxEvent.claim_token == event.claim_token)
                .with_for_update()
            )
            if row is None or row.delivered_at is not None:
                raise RuntimeError("Outbox event lease is no longer valid.")
            row.delivered_at = _database_now(session)
            row.claimed_at = None
            row.claim_token = None

    def release_failed(
        self,
        event: ClaimedOutboxEvent,
        *,
        failure_detail: str,
        retry_policy: OutboxRetryPolicy,
    ) -> bool:
        """Release a failed event, returning whether it became a dead letter."""

        if not failure_detail.strip():
            raise ValueError("failure_detail is required.")
        with self._sessions.begin() as session:
            row = session.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == event.id, OutboxEvent.claim_token == event.claim_token)
                .with_for_update()
            )
            if row is None or row.delivered_at is not None:
                raise RuntimeError("Outbox event lease is no longer valid.")
            now = _database_now(session)
            row.attempt_count += 1
            row.last_error = failure_detail
            row.claimed_at = None
            row.claim_token = None
            if row.attempt_count >= retry_policy.max_attempts:
                row.dead_lettered_at = now
                return True
            row.available_at = now + retry_policy.retry_delay(row.attempt_count)
            return False

    def purge_delivered(self, *, retention: timedelta) -> int:
        if retention <= timedelta(0):
            raise ValueError("retention must be positive.")
        with self._sessions.begin() as session:
            cutoff = _database_now(session) - retention
            result = session.execute(
                delete(OutboxEvent).where(OutboxEvent.delivered_at.is_not(None), OutboxEvent.delivered_at < cutoff)
            )
            return int(result.rowcount or 0)


def _database_now(session: Session) -> datetime:
    from sqlalchemy import func, select

    return session.scalar(select(func.now()))
