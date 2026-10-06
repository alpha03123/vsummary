from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dataclasses import replace
from tests._api_fixtures import make_api_container, make_workspace_services, replace_test_services
from unittest.mock import create_autospec

from fastapi.testclient import TestClient

from backend.local.http.app import create_app
from backend.video_summary.infrastructure.persistence.control_plane_repository import SubmittedJob
from backend.video_summary.infrastructure.persistence.job_repository import JobEventSnapshot, SqlJobRepository
from backend.video_summary.library.models import (
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoLibraryDTO,
    VideoSourceDTO,
    WorkspaceDTO,
)
from backend.video_summary.library.ports import VideoLibraryReader
from backend.video_summary.library.usecases import GetVideoSource, ListVideoLibrary
from tests._job_fixtures import job_snapshot


class GenerationStatusApiTests(unittest.TestCase):
    def test_video_generation_status_returns_last_durable_job_event(self) -> None:
        container = _build_container()
        started_at = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)
        container = replace(container, job_repository=create_autospec(SqlJobRepository, instance=True, spec_set=True))
        container.job_repository.latest_for_resource.return_value = job_snapshot(
            id="job-1", started_at=started_at,
        )
        container.job_repository.latest_event.return_value = JobEventSnapshot(
            sequence=2, status="running", stage="publish", progress=99.0,
            detail="正在保存生成结果", occurred_at=started_at + timedelta(seconds=12),
            started_at=started_at,
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
            "started_at": started_at.timestamp(),
            "elapsed_seconds": 12.0,
        })
        container.job_repository.latest_for_resource.assert_called_once_with(
            workspace_id="workspace-1", resource_id="video-1",
            operations=("generate_summary", "generate_transcript", "process_agent_video"),
        )

    def test_queued_generation_has_no_start_time_or_elapsed_duration(self) -> None:
        container = _build_container()
        container = replace(container, job_repository=create_autospec(SqlJobRepository, instance=True, spec_set=True))
        container.job_repository.latest_for_resource.return_value = job_snapshot(id="job-1", status="queued")
        container.job_repository.latest_event.return_value = None

        response = TestClient(create_app(container)).get("/api/videos/series-1/video-1/generate/status")

        self.assertEqual(response.status_code, 200)
        snapshot = response.json()["snapshot"]
        self.assertEqual(snapshot["status"], "queued")
        self.assertEqual(snapshot["progress"], 0.0)
        self.assertIsNone(snapshot["started_at"])
        self.assertIsNone(snapshot["elapsed_seconds"])

    def test_series_generate_submits_durable_parent_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository()
        container = replace(container, job_repository=repository)
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate", json={"processing_mode": "summary"})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(repository.calls[0]["operation"], "generate_series_batch")
        self.assertEqual(repository.calls[0]["resource_id"], "series-1")
        self.assertEqual(repository.calls[0]["request_payload"]["series_id"], "series-1")

    def test_series_missing_media_is_rejected_before_submission(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository()
        container = replace(container, job_repository=repository)
        source = create_autospec(GetVideoSource, instance=True, spec_set=True)
        source.run.return_value = None
        replace_test_services(container, get_video_source=source)
        response = TestClient(create_app(container)).post('/api/series/series-1/generate')
        self.assertEqual(response.status_code, 409)
        self.assertIn('重新上传', response.json()['detail'])
        self.assertEqual(repository.calls, [])

    def test_duplicate_series_submit_returns_existing_parent_job(self) -> None:
        container = _build_container()
        container = replace(container, job_repository=_FakeJobRepository(conflict=True))

        response = TestClient(create_app(container)).post("/api/series/series-1/generate")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-existing")

    def test_series_submit_refuses_when_any_pending_video_is_already_active(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository(active_video=True)
        container = replace(container, job_repository=repository)

        response = TestClient(create_app(container)).post("/api/series/series-1/generate")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(repository.calls, [])

    def test_series_cancel_requests_durable_parent_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository()
        container = replace(container, job_repository=repository)

        response = TestClient(create_app(container)).post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(response.json()["status"], "cancelled")

    def test_video_generate_submits_a_durable_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository()
        container = replace(container, job_repository=repository)
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/video-1/generate")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(repository.calls[0]["operation"], "generate_summary")
        self.assertEqual(repository.calls[0]["active_key"], "video:video-1:generate_summary")

    def test_duplicate_video_generate_returns_the_existing_durable_job(self) -> None:
        container = _build_container()
        repository = _FakeJobRepository(conflict=True)
        container = replace(container, job_repository=repository)
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/video-1/generate")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-existing")
        self.assertEqual(response.json()["status"], "running")

def _build_container():
    reader = create_autospec(VideoLibraryReader, instance=True, spec_set=True)
    reader.get_video_source.side_effect = lambda series_id, video_id: VideoSourceDTO(
        series_id=series_id, video_id=video_id, title="Video", source_name=Path(__file__).name,
        source_path=Path(__file__), output_dir=Path(__file__).parent, processed=False,
    )
    library = VideoLibraryDTO(
        workspace=WorkspaceDTO(id="workspace-1", title="Workspace"),
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
    reader.get_workspace.return_value = library.workspace
    reader.list_series.return_value = library.series
    return make_api_container(services=make_workspace_services(
        list_video_library=ListVideoLibrary(reader), get_video_source=GetVideoSource(reader),
    ))


class _FakeJobRepository:
    def __init__(self, conflict: bool = False, active_video: bool = False) -> None:
        self.calls: list[dict[str, object]] = []
        self.conflict = conflict
        self.active_video = active_video

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        if self.conflict:
            from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError

            raise ControlPlaneConflictError("An active job already exists for this resource.")
        return SubmittedJob(id="job-1", created=True, status="queued")

    def active_for_resource(self, **kwargs):
        if self.active_video and kwargs["resource_id"] in {"video-1", "video-2"}:
            return job_snapshot(id="active-video")
        if not self.conflict:
            return None
        return job_snapshot(id="job-existing")

    def request_cancel_series_generation(self, **_kwargs):
        return [
            job_snapshot(
                id="job-1",
                resource_id="series-1",
                resource_type="series",
                operation="generate_series_batch",
                status="cancelled",
            )
        ]


if __name__ == "__main__":
    unittest.main()
