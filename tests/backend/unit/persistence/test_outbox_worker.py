from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.persistence.outbox_repository import ClaimedOutboxEvent, OutboxRetryPolicy
from backend.video_summary.infrastructure.persistence.outbox_worker import SqlOutboxWorker


class _Repository:
    def __init__(self, events: list[ClaimedOutboxEvent]) -> None:
        self.events = events
        self.confirmed: list[str] = []
        self.released: list[str] = []

    def claim_batch(self, **_kwargs):
        result, self.events = self.events, []
        return result

    def confirm_delivered(self, event):
        self.confirmed.append(event.id)

    def release_failed(self, event, *, failure_detail, retry_policy):
        self.released.append((event.id, failure_detail, retry_policy))
        return False



def _event(*, event_type: str = "content_published") -> ClaimedOutboxEvent:
    return ClaimedOutboxEvent(
        id="event-1",
        workspace_id="workspace-1",
        claim_token="lease",
        event_type=event_type,
        aggregate_type="video_content",
        aggregate_id="video-1",
        payload={"video_id": "video-1"},
        attempt_count=0,
    )


class SqlOutboxWorkerTests(unittest.TestCase):
    def test_confirms_only_after_handler_succeeds(self) -> None:
        repository = _Repository([])
        worker = SqlOutboxWorker(
            repository=repository,
            workspace_id="workspace-1",
            handlers={"content_published": lambda _event: None},
        )

        worker._dispatch(_event())

        self.assertEqual(repository.confirmed, ["event-1"])
        self.assertEqual(repository.released, [])

    def test_releases_event_when_handler_fails_or_is_missing(self) -> None:
        repository = _Repository([])
        worker = SqlOutboxWorker(
            repository=repository,
            workspace_id="workspace-1",
            handlers={"content_published": lambda _event: (_ for _ in ()).throw(RuntimeError("boom"))},
        )

        worker._dispatch(_event())
        worker._dispatch(_event(event_type="unknown"))

        self.assertEqual(repository.confirmed, [])
        self.assertEqual([event_id for event_id, _detail, _policy in repository.released], ["event-1", "event-1"])

    def test_retry_policy_is_bounded_exponential_backoff(self) -> None:
        policy = OutboxRetryPolicy(max_attempts=4, initial_delay_seconds=2, max_delay_seconds=5)

        self.assertEqual(policy.retry_delay(1).total_seconds(), 2)
        self.assertEqual(policy.retry_delay(2).total_seconds(), 4)
        self.assertEqual(policy.retry_delay(3).total_seconds(), 5)
        self.assertEqual(policy.retry_delay(4).total_seconds(), 5)

    def test_claims_are_scoped_to_worker_workspace_and_retry_limit(self) -> None:
        repository = _Repository([])
        worker = SqlOutboxWorker(
            repository=repository,
            workspace_id="workspace-1",
            handlers={},
            retry_policy=OutboxRetryPolicy(max_attempts=3, initial_delay_seconds=1, max_delay_seconds=4),
        )

        calls = []

        def claim_batch(**kwargs):
            calls.append(kwargs)
            worker._stop.set()
            return []

        repository.claim_batch = claim_batch
        worker._run()

        self.assertEqual(calls[0]["workspace_id"], "workspace-1")
        self.assertEqual(calls[0]["max_attempts"], 3)
