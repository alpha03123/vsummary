from tests._api_fixtures import mock_service
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository

from backend.api.adapters.durable_workspace_index_refresher import (
    DurableWorkspaceIndexRefresher,
    submit_workspace_index_refresh,
)
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError


def test_all_index_mutations_submit_one_workspace_refresh_job() -> None:
    calls: list[str] = []
    refresher = DurableWorkspaceIndexRefresher(lambda: calls.append("refresh"))

    refresher.refresh()
    refresher.refresh_all()
    refresher.upsert_video("series", "video")
    refresher.delete_video("series", "video")
    refresher.delete_series("series")

    assert calls == ["refresh"] * 5


def test_refresh_submission_is_workspace_scoped_and_coalesces_active_job() -> None:
    submissions: list[dict[str, object]] = []
    repository = mock_service(SqlJobRepository)
    repository.submit.side_effect = lambda **kwargs: submissions.append(kwargs)

    submit_workspace_index_refresh(repository=repository, workspace_id="workspace-1")

    assert submissions == [{
        "workspace_id": "workspace-1",
        "resource_type": "workspace",
        "resource_id": "workspace-1",
        "operation": "refresh_rag_index",
        "request_payload": {"workspace_id": "workspace-1"},
        "active_key": "workspace:workspace-1:refresh_rag_index",
        "idempotency_scope_id": None,
        "idempotency_key": None,
    }]

    repository.submit.side_effect = ControlPlaneConflictError("active")
    submit_workspace_index_refresh(
        repository=repository,
        workspace_id="workspace-1",
    )
