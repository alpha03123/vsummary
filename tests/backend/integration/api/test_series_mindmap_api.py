from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests._workspace_scope import attach_workspace_scope
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
        return SimpleNamespace(id="job-series-mindmap", status="queued")

    def active_for_resource(self, **_kwargs):
        return SimpleNamespace(id="job-active", status="running") if self.conflict else None


def _container(*, mindmap_node: dict | None = None, conflict: bool = False) -> SimpleNamespace:
    mindmap = (
        SimpleNamespace(series_id="s1", video_id="", title="Series", mindmap=mindmap_node)
        if mindmap_node is not None
        else None
    )
    return attach_workspace_scope(SimpleNamespace(
        root_dir=None,
        job_repository=_Jobs(conflict=conflict),
        get_series_mindmap=SimpleNamespace(run=lambda _series: mindmap),
    ))


class SeriesMindmapApiTests(unittest.TestCase):
    def test_get_series_mindmap_returns_tree(self) -> None:
        response = TestClient(create_app(_container(mindmap_node={"id": "root", "title": "T", "children": []}))).get("/api/series/s1/mindmap")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "T")

    def test_submit_series_mindmap_returns_durable_job(self) -> None:
        container = _container()
        response = TestClient(create_app(container)).post("/api/series/s1/mindmap/generate", json={"max_depth": 3})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-series-mindmap")
        self.assertEqual(container.job_repository.calls[0]["workspace_id"], "workspace-1")
        self.assertEqual(container.job_repository.calls[0]["operation"], "generate_series_mindmap")
        self.assertEqual(container.job_repository.calls[0]["request_payload"], {"series_id": "s1", "max_depth": 3})

    def test_duplicate_submit_returns_active_job(self) -> None:
        response = TestClient(create_app(_container(conflict=True))).post("/api/series/s1/mindmap/generate")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-active")

    def test_legacy_tracker_endpoint_is_not_registered(self) -> None:
        response = TestClient(create_app(_container())).get("/api/series/s1/mindmap/generate/progress")
        self.assertEqual(response.status_code, 404)
