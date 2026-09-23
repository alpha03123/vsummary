from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests._workspace_scope import attach_workspace_scope
from backend.local.http.app import create_app
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError
from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO


class _Jobs:
    def __init__(self, *, conflict: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.conflict = conflict

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        if self.conflict:
            raise ControlPlaneConflictError("active job")
        return SimpleNamespace(id="job-cards", status="queued")

    def active_for_resource(self, **_kwargs):
        return SimpleNamespace(id="job-active", status="running") if self.conflict else None


def _container(*, conflict: bool = False) -> SimpleNamespace:
    library = SimpleNamespace(series=[LibrarySeriesDTO(id="s1", title="Series", videos=[LibraryVideoCardDTO(id="v1", title="Video", source_name="v1.mp4", processed=True, status="ready")])])
    return attach_workspace_scope(SimpleNamespace(
        root_dir=None,
        job_repository=_Jobs(conflict=conflict),
        list_video_library=SimpleNamespace(run=lambda: library),
        get_video_source=SimpleNamespace(run=lambda _series, _video: None),
    ))


class DurableKnowledgeCardsJobApiTests(unittest.TestCase):
    def test_submit_returns_durable_job(self) -> None:
        container = _container()
        response = TestClient(create_app(container)).post("/api/videos/s1/v1/knowledge-cards/generate")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-cards")
        self.assertEqual(container.job_repository.calls[0]["workspace_id"], "workspace-1")
        self.assertEqual(container.job_repository.calls[0]["operation"], "generate_video_knowledge_cards")
        self.assertEqual(container.job_repository.calls[0]["request_payload"], {"series_id": "s1", "video_id": "v1"})

    def test_duplicate_submit_returns_active_job(self) -> None:
        response = TestClient(create_app(_container(conflict=True))).post("/api/videos/s1/v1/knowledge-cards/generate")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-active")
