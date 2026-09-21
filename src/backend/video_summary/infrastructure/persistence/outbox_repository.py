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
    claim_token: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, object]
    attempt_count: int


class SqlOutboxRepository:
    """MySQL outbox with lease ownership, explicit confirmation, and cleanup."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def claim_batch(self, *, worker_id: str, lease_seconds: int, limit: int = 25) -> list[ClaimedOutboxEvent]:
        if not worker_id.strip() or lease_seconds < 1 or limit < 1:
            raise ValueError("worker_id, a positive lease_seconds, and a positive limit are required.")
        with self._sessions.begin() as session:
            now = _database_now(session)
            expired_before = now - timedelta(seconds=lease_seconds)
            events = session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.delivered_at.is_(None),
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

    def release_failed(self, event: ClaimedOutboxEvent) -> None:
        with self._sessions.begin() as session:
            row = session.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == event.id, OutboxEvent.claim_token == event.claim_token)
                .with_for_update()
            )
            if row is None or row.delivered_at is not None:
                raise RuntimeError("Outbox event lease is no longer valid.")
            row.attempt_count += 1
            row.claimed_at = None
            row.claim_token = None

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
