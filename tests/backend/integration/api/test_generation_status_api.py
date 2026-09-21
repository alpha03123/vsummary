from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


from backend.local.http.app import create_app
from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO


class GenerationStatusApiTests(unittest.TestCase):
    def test_video_generation_status_returns_last_durable_job_event(self) -> None:
        container = _build_container()
        container.job_repository = SimpleNamespace(
            latest_for_resource=lambda **_kwargs: SimpleNamespace(
                id="job-1", status="running", failure_detail=None
            ),
            latest_event=lambda _job_id, **_kwargs: SimpleNamespace(
                stage="publish", progress=99.0, detail="正在保存生成结果"
            ),
        )
        client = TestClient(create_app(container))

        response = client.get("/api/videos/series-1/video-1/generate/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(response.json()["snapshot"], {
            "status": "running",
            "stage": "publish",
            "progress": 99.0,
            "detail": "正在保存生成结果",
            "error": None,
        })

    def test_series_generate_submits_durable_parent_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository()
        container.job_repository = repository
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate", json={"processing_mode": "summary"})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(repository.calls[0]["operation"], "generate_series_batch")
        self.assertEqual(repository.calls[0]["resource_id"], "series-1")
        self.assertEqual(repository.calls[0]["request_payload"]["series_id"], "series-1")

    def test_duplicate_series_submit_returns_existing_parent_job(self) -> None:
        container = _build_container()
        container.job_repository = _FakeJobRepository(conflict=True)

        response = TestClient(create_app(container)).post("/api/series/series-1/generate")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-existing")

    def test_series_cancel_requests_durable_parent_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository()
        container.job_repository = repository

        response = TestClient(create_app(container)).post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(response.json()["status"], "cancelled")

    def test_video_generate_submits_a_durable_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository()
        container.sql_workspace = SimpleNamespace(get_workspace=lambda: SimpleNamespace(id="workspace-1"))
        container.job_repository = repository
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/video-1/generate")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(repository.calls[0]["operation"], "generate_summary")
        self.assertEqual(repository.calls[0]["active_key"], "video:video-1:generate_summary")

    def test_duplicate_video_generate_returns_the_existing_durable_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository(conflict=True)
        container.sql_workspace = SimpleNamespace(get_workspace=lambda: SimpleNamespace(id="workspace-1"))
        container.job_repository = repository
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/video-1/generate")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-existing")
        self.assertEqual(response.json()["status"], "running")

def _build_container():
    source_runner = SimpleNamespace(
        run=lambda series_id, video_id: SimpleNamespace(source_path=Path(__file__))
    )
    library = SimpleNamespace(
        series=[
            LibrarySeriesDTO(
                id="series-1",
                title="Series 1",
                videos=[
                    LibraryVideoCardDTO(
                        id="video-1",
                        title="Video 1",
                        source_name="video-1.mp4",
                        processed=False,
                        status="pending",
                    ),
                    LibraryVideoCardDTO(
                        id="video-2",
                        title="Video 2",
                        source_name="video-2.mp4",
                        processed=False,
                        status="pending",
                    ),
                ],
            ),
        ],
    )
    return SimpleNamespace(
        root_dir=None,
        sql_workspace=SimpleNamespace(workspace_id="workspace-1"),
        list_video_library=SimpleNamespace(run=lambda: library),
        get_video_source=source_runner,
    )


class _FakeJobRepository:
    def __init__(self, conflict: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.conflict = conflict

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        if self.conflict:
            from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError

            raise ControlPlaneConflictError("An active job already exists for this resource.")
        return SimpleNamespace(id="job-1", status="queued")

    def active_for_resource(self, **kwargs):
        if not self.conflict:
            return None
        return SimpleNamespace(id="job-existing", status="running")

    def request_cancel_series_generation(self, **_kwargs):
        return [
            SimpleNamespace(
                id="job-1",
                resource_id="series-1",
                resource_type="series",
                operation="generate_series_batch",
                status="cancelled",
            )
        ]


if __name__ == "__main__":
    unittest.main()
