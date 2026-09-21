from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.persistence.outbox_repository import ClaimedOutboxEvent
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

    def release_failed(self, event):
        self.released.append(event.id)



def _event(*, event_type: str = "content_published") -> ClaimedOutboxEvent:
    return ClaimedOutboxEvent(
        id="event-1",
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
        worker = SqlOutboxWorker(repository=repository, handlers={"content_published": lambda _event: None})

        worker._dispatch(_event())

        self.assertEqual(repository.confirmed, ["event-1"])
        self.assertEqual(repository.released, [])

    def test_releases_event_when_handler_fails_or_is_missing(self) -> None:
        repository = _Repository([])
        worker = SqlOutboxWorker(repository=repository, handlers={"content_published": lambda _event: (_ for _ in ()).throw(RuntimeError("boom"))})

        worker._dispatch(_event())
        worker._dispatch(_event(event_type="unknown"))

        self.assertEqual(repository.confirmed, [])
        self.assertEqual(repository.released, ["event-1", "event-1"])
