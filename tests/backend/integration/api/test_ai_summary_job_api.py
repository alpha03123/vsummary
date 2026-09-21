from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.local.http.app import create_app
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError


class _Jobs:
    def __init__(self, *, conflict: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.conflict = conflict

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        if self.conflict:
            raise ControlPlaneConflictError("active job")
        return SimpleNamespace(id="job-ai-summary", status="queued")

    def active_for_resource(self, **_kwargs):
        return SimpleNamespace(id="job-active", status="running") if self.conflict else None


def _container(*, conflict: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        root_dir=None,
        sql_workspace=SimpleNamespace(workspace_id="workspace-1"),
        job_repository=_Jobs(conflict=conflict),
    )


class DurableAiSummaryJobApiTests(unittest.TestCase):
    def test_submit_returns_durable_job_with_template(self) -> None:
        container = _container()
        response = TestClient(create_app(container)).post(
            "/api/videos/s1/v1/ai-summary/generate",
            json={"template": "tutorial"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-ai-summary")
        self.assertEqual(container.job_repository.calls[0]["workspace_id"], "workspace-1")
        self.assertEqual(container.job_repository.calls[0]["operation"], "generate_video_ai_summary")
        self.assertEqual(container.job_repository.calls[0]["request_payload"], {"series_id": "s1", "video_id": "v1", "template": "tutorial"})

    def test_duplicate_submit_returns_active_job(self) -> None:
        response = TestClient(create_app(_container(conflict=True))).post("/api/videos/s1/v1/ai-summary/generate")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-active")
