from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from backend.api.routes.jobs import refresh_workspace_index, workspace_index_status
from backend.core.context import WorkspaceContext
from tests._job_fixtures import job_snapshot


def test_missing_index_is_reported_even_without_a_job():
    repository = Mock()
    repository.latest_for_resource.return_value = None
    services = Mock()
    services.inspect_agent_workspace_indexes.return_value = {"index_state": "missing", "video_states": {"v": "missing"}}
    context = WorkspaceContext("workspace", "actor", "request")
    result = workspace_index_status(repository, services, context, series_id="series")
    assert result["status"] == "idle"
    assert result["index_state"] == "missing"
    assert result["video_states"] == {"v": "missing"}
    repository.index_refresh_plan.assert_called_once_with("workspace")


def test_status_keeps_index_health_separate_from_historical_failed_job():
    repository = Mock()
    repository.latest_for_resource.return_value = job_snapshot(id="old", status="failed", failure_detail="old failure")
    repository.events.return_value = []
    services = Mock()
    services.inspect_agent_workspace_indexes.return_value = {"index_state": "ready", "video_states": {"v": "ready"}}
    result = workspace_index_status(repository, services, WorkspaceContext("workspace", "actor", "request"))
    assert result["status"] == "failed"
    assert result["index_state"] == "ready"


def test_rebuild_uses_authenticated_workspace():
    repository = Mock()
    services = Mock(embedding_provider="fastembed")
    services.rag_model_manager.is_downloaded.return_value = True
    context = WorkspaceContext("workspace", "actor", "request")
    assert refresh_workspace_index(repository, services, context) == {"status": "queued"}
    repository.request_index_refresh.assert_called_once_with("workspace")


def test_rebuild_without_the_embedding_model_asks_for_the_download_instead_of_queueing():
    repository = Mock()
    services = Mock(embedding_provider="fastembed")
    services.rag_model_manager.is_downloaded.return_value = False
    with pytest.raises(HTTPException) as caught:
        refresh_workspace_index(repository, services, WorkspaceContext("workspace", "actor", "request"))
    assert caught.value.status_code == 409 and "下载 RAG 向量模型" in caught.value.detail
    repository.request_index_refresh.assert_not_called()
