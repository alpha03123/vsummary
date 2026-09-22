"""Background dispatcher for explicitly handled Outbox event types."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from threading import Event, Thread
from uuid import uuid4

from backend.video_summary.infrastructure.persistence.outbox_repository import (
    ClaimedOutboxEvent,
    OutboxRetryPolicy,
    SqlOutboxRepository,
)


LOGGER = logging.getLogger(__name__)


class SqlOutboxWorker:
    def __init__(
        self,
        *,
        repository: SqlOutboxRepository,
        workspace_id: str,
        handlers: dict[str, Callable[[ClaimedOutboxEvent], None]],
        poll_seconds: float = 1.0,
        lease_seconds: int = 60,
        retention_days: int = 14,
        retry_policy: OutboxRetryPolicy = OutboxRetryPolicy(),
    ) -> None:
        if not workspace_id.strip():
            raise ValueError("workspace_id is required.")
        self._repository = repository
        self._workspace_id = workspace_id
        self._handlers = handlers
        self._poll_seconds = poll_seconds
        self._lease_seconds = lease_seconds
        self._retention_days = retention_days
        self._retry_policy = retry_policy
        self._worker_id = f"outbox-{uuid4().hex}"
        self._stop = Event()
        self._thread: Thread | None = None
        self._cycles = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name=f"vsummary-outbox:{self._worker_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                events = self._repository.claim_batch(
                    workspace_id=self._workspace_id,
                    worker_id=self._worker_id,
                    lease_seconds=self._lease_seconds,
                    max_attempts=self._retry_policy.max_attempts,
                )
                for event in events:
                    self._dispatch(event)
                self._cycles += 1
                if self._cycles % 60 == 0:
                    self._repository.purge_delivered(retention=timedelta(days=self._retention_days))
                if not events:
                    self._stop.wait(self._poll_seconds)
            except Exception:
                LOGGER.exception("outbox claim loop failed")
                self._stop.wait(self._poll_seconds)

    def _dispatch(self, event: ClaimedOutboxEvent) -> None:
        handler = self._handlers.get(event.event_type)
        if handler is None:
            LOGGER.error("outbox event has no handler", extra={"event_type": event.event_type, "event_id": event.id})
            self._release_failed(event, f"No handler is registered for event type '{event.event_type}'.")
            return
        try:
            handler(event)
            self._repository.confirm_delivered(event)
        except Exception as error:
            LOGGER.exception("outbox handler failed", extra={"event_type": event.event_type, "event_id": event.id})
            self._release_failed(event, f"{type(error).__name__}: {error}")

    def _release_failed(self, event: ClaimedOutboxEvent, failure_detail: str) -> None:
        dead_lettered = self._repository.release_failed(
            event,
            failure_detail=failure_detail,
            retry_policy=self._retry_policy,
        )
        if dead_lettered:
            LOGGER.error(
                "outbox event moved to dead letter",
                extra={"event_type": event.event_type, "event_id": event.id, "attempt_count": event.attempt_count + 1},
            )
