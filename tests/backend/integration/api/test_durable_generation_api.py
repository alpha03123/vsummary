from __future__ import annotations

from tests._api_fixtures import make_api_container, make_workspace_services

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.local.http.app import create_app
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from backend.video_summary.infrastructure.persistence.models import Job, JobEvent
from backend.video_summary.library.usecases import GetSeriesMindmap, GetVideoSource, ListVideoLibrary


@pytest.fixture
def generation_client(stored_video, mysql_sessions):
    workspace, series_id, video_id = stored_video
    container = make_api_container(
        job_repository=SqlJobRepository(mysql_sessions),
        services=make_workspace_services(
            workspace_id=workspace.workspace_id,
            list_video_library=ListVideoLibrary(workspace), get_video_source=GetVideoSource(workspace),
            get_series_mindmap=GetSeriesMindmap(workspace),
        ),
    )
    return TestClient(create_app(container)), workspace.workspace_id, series_id, video_id


@pytest.mark.parametrize("target,body,operation", [
    ("knowledge-cards", {}, "generate_video_knowledge_cards"),
    ("ai-summary", {"template": "tutorial"}, "generate_video_ai_summary"),
    ("mindmap", {"max_depth": 4}, "generate_video_mindmap"),
    ("series-mindmap", {"max_depth": 3}, "generate_series_mindmap"),
])
def test_submission_and_duplicate_request_persist_one_job(generation_client, mysql_sessions, target, body, operation) -> None:
    client, workspace_id, series_id, video_id = generation_client
    is_series = target == "series-mindmap"
    url = f"/api/series/{series_id}/mindmap/generate" if is_series else f"/api/videos/{series_id}/{video_id}/{target}/generate"
    first = client.post(url, json=body)
    repeated = client.post(url, json=body)

    assert first.status_code == repeated.status_code == 202
    assert first.json()["job_id"] == repeated.json()["job_id"]
    assert first.json()["status"] == repeated.json()["status"] == "queued"
    with mysql_sessions() as session:
        jobs = session.scalars(select(Job).where(Job.workspace_id == workspace_id)).all()
        events = session.scalars(select(JobEvent).join(Job).where(Job.workspace_id == workspace_id)).all()
    assert len(jobs) == len(events) == 1
    job = jobs[0]
    assert job.id == first.json()["job_id"] == events[0].job_id
    assert job.resource_id == (series_id if is_series else video_id)
    assert job.resource_type == ("series" if is_series else "video")
    assert job.operation == operation
    expected_payload = {"series_id": series_id, **body}
    if not is_series:
        expected_payload["video_id"] = video_id
    expected_payload["_execution_context"] = {
        "actor_id": "test-user",
        "request_id": first.headers["X-Request-ID"],
    }
    assert job.request_payload == expected_payload


@pytest.mark.parametrize("target", ["knowledge-cards", "mindmap"])
def test_missing_video_does_not_create_job(generation_client, mysql_sessions, target) -> None:
    client, workspace_id, series_id, _ = generation_client
    response = client.post(f"/api/videos/{series_id}/missing/{target}/generate", json={})
    assert response.status_code == 404
    with mysql_sessions() as session:
        assert session.scalar(select(Job.id).where(Job.workspace_id == workspace_id)) is None


@pytest.mark.parametrize("path", [
    "/api/videos/{series_id}/{video_id}/mindmap/generate/progress",
    "/api/series/{series_id}/mindmap/generate/progress",
])
def test_removed_progress_endpoint_is_not_registered(generation_client, path) -> None:
    client, _, series_id, video_id = generation_client
    assert client.get(path.format(series_id=series_id, video_id=video_id)).status_code == 404


def test_series_mindmap_returns_the_persisted_tree(generation_client, stored_video) -> None:
    client, _, series_id, _ = generation_client
    workspace, _, _ = stored_video
    tree = {"id": "root", "title": "Series map", "children": [{"id": "child", "title": "Chapter", "children": []}]}
    workspace.save_series_mindmap(series_id, mindmap=tree)
    response = client.get(f"/api/series/{series_id}/mindmap")
    assert response.status_code == 200
    assert response.json() == tree


def test_agent_video_job_can_be_recovered_and_cancelled_by_id(generation_client) -> None:
    client, _, series_id, video_id = generation_client
    submitted = client.post(
        f"/api/agent/series/{series_id}/process",
        json={"video_ids": [video_id], "processing_mode": "summary"},
    )
    assert submitted.status_code == 200
    jobs = submitted.json()["jobs"]
    assert len(jobs) == 1
    job_id = jobs[0]["job_id"]
    assert jobs[0]["resource"] == {"type": "video", "id": video_id}

    recovered = client.get(f"/api/videos/{series_id}/{video_id}/generate/status")
    assert recovered.status_code == 200
    assert recovered.json()["job_id"] == job_id
    assert recovered.json()["snapshot"]["status"] == "queued"

    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    after_cancel = client.get(f"/api/videos/{series_id}/{video_id}/generate/status")
    assert after_cancel.json()["job_id"] == job_id
    assert after_cancel.json()["snapshot"]["status"] == "cancelled"
