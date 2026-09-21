from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from backend.core.context import WorkspaceContext
from backend.core.quota import QuotaReservation
from backend.core.request_context import bind_workspace_context
from backend.video_summary.infrastructure.persistence.control_plane_repository import SubmittedJob
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository


class _QuotaGuard:
    def __init__(self) -> None:
        self.reservations: list[tuple[WorkspaceContext, str, str]] = []
        self.releases: list[tuple[str, str]] = []

    def reserve_job(self, context, operation, _estimate, idempotency_key):
        self.reservations.append((context, operation, idempotency_key))
        return QuotaReservation(id="reservation-1")

    def settle(self, _reservation_id, _actual) -> None:
        return None

    def release(self, reservation_id, reason) -> None:
        self.releases.append((reservation_id, reason))


def test_job_submission_records_request_reservation() -> None:
    quota = _QuotaGuard()
    repository = SqlJobRepository(Mock(), quota_guard=quota)
    control = Mock(submit_job=Mock(return_value=SubmittedJob(id="job-1", created=True, status="queued")))
    repository._control = control
    context = WorkspaceContext("workspace-1", "actor-1", "request-1")

    with bind_workspace_context(context):
        repository.submit(
            workspace_id="workspace-1",
            resource_type="video",
            resource_id="video-1",
            operation="generate_summary",
            request_payload={"series_id": "series-1"},
            active_key="video:video-1:generate_summary",
            idempotency_scope_id=None,
            idempotency_key=None,
        )

    payload = control.submit_job.call_args.kwargs["request_payload"]
    assert payload["_quota_reservation"] == {
        "id": "reservation-1",
        "workspace_id": "workspace-1",
        "actor_id": "actor-1",
        "request_id": "request-1",
    }
    assert quota.releases == []


def test_reused_job_releases_new_reservation() -> None:
    quota = _QuotaGuard()
    repository = SqlJobRepository(Mock(), quota_guard=quota)
    repository._control = SimpleNamespace(submit_job=lambda **_kwargs: SubmittedJob(id="job-1", created=False, status="running"))

    with bind_workspace_context(WorkspaceContext("workspace-1", "actor-1", "request-1")):
        repository.submit(
            workspace_id="workspace-1",
            resource_type="video",
            resource_id="video-1",
            operation="generate_summary",
            request_payload={},
            active_key="video:video-1:generate_summary",
            idempotency_scope_id=None,
            idempotency_key=None,
        )

    assert quota.releases == [("reservation-1", "existing job reused")]
