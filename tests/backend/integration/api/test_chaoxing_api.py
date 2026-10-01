from __future__ import annotations

import unittest
from dataclasses import replace
from tests._api_fixtures import make_api_container, mock_service

from fastapi.testclient import TestClient

from backend.chaoxing.chaoxing_api import (
    ChaoxingCourseImporter,
    ChaoxingChapterRecord,
    ChaoxingCourseRecord,
    ChaoxingInitCancelled,
    ChaoxingVideoRecord,
)
from backend.local.http.app import create_app
from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError, SubmittedJob
from backend.video_summary.infrastructure.persistence.job_repository import JobSnapshot
from tests._job_fixtures import job_snapshot


class ChaoxingApiTests(unittest.TestCase):
    def test_status_reports_initialization_state(self) -> None:
        response = TestClient(create_app(_build_container())).get("/api/linked/chaoxing/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"initialized": True})

    def test_status_returns_clear_error_when_dependency_is_missing(self) -> None:
        container = _build_container()
        container.chaoxing_importer.is_initialized.side_effect = RuntimeError("缺少依赖")

        response = TestClient(create_app(container)).get("/api/linked/chaoxing/status")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "缺少依赖")

    def test_import_course_submits_durable_job(self) -> None:
        container = _build_container()
        response = TestClient(create_app(container)).post("/api/linked/chaoxing/import/course", json={"course_key": "course-1"})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json(),
            {"job_id": "job-1", "status": "queued", "series_id": "chaoxing-course-1"},
        )
        self.assertEqual(
            container.job_repository.submissions,
            [{"course_key": "course-1", "operation": "import_chaoxing_course", "resource_id": "chaoxing-course-1"}],
        )

    def test_import_course_reuses_active_job_after_active_key_conflict(self) -> None:
        container = _build_container(conflict=True)
        response = TestClient(create_app(container)).post("/api/linked/chaoxing/import/course", json={"course_key": "course-1"})

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-active")

    def test_cancel_import_course_requests_durable_job_cancellation(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))
        client.post("/api/linked/chaoxing/import/course", json={"course_key": "course-1"})

        response = client.post("/api/linked/chaoxing/import/course/job-1/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cancelled", "job_id": "job-1"})

    def test_init_returns_conflict_when_login_is_cancelled(self) -> None:
        container = _build_container()
        container.chaoxing_importer.init.side_effect = ChaoxingInitCancelled("超星初始化已中断")

        response = TestClient(create_app(container)).post("/api/linked/chaoxing/init")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "超星初始化已中断")

    def test_cancel_init_delegates_to_importer(self) -> None:
        container = _build_container()
        response = TestClient(create_app(container)).post("/api/linked/chaoxing/init/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cancelled"})
        container.chaoxing_importer.cancel_init.assert_called_once_with()


class _JobRepository:
    def __init__(self, *, conflict: bool) -> None:
        self._conflict = conflict
        self.submissions: list[dict[str, str]] = []
        self._jobs: dict[str, JobSnapshot] = {"job-active": job_snapshot(id="job-active", status="running")}

    def submit(self, *, request_payload, operation, resource_id, **_kwargs):
        self.submissions.append({"course_key": request_payload["course_key"], "operation": operation, "resource_id": resource_id})
        if self._conflict:
            raise ControlPlaneConflictError("active job exists")
        self._jobs["job-1"] = job_snapshot(id="job-1", status="queued", resource_type="series", resource_id=resource_id, operation=operation)
        return SubmittedJob(id="job-1", status="queued", created=True)

    def active_for_resource(self, **_kwargs):
        return self._jobs["job-active"] if self._conflict else None

    def request_cancel(self, job_id, **_kwargs):
        snapshot = self._jobs.get(job_id)
        if snapshot is None:
            return None
        self._jobs[job_id] = replace(snapshot, status="cancelled", cancel_requested=True)
        return self._jobs[job_id]


def _build_container(*, conflict: bool = False):
    return make_api_container(
        job_repository=_JobRepository(conflict=conflict),
        chaoxing_importer=mock_service(
            ChaoxingCourseImporter, is_initialized=True, init=None,
            list_courses=[ChaoxingCourseRecord(course_key="course-1", title="超星课程", teacher="老师", open_time="")],
            list_chapters=[ChaoxingChapterRecord(chapter_key="chapter-1", title="第一章", order="1")],
            list_videos=[ChaoxingVideoRecord(video_key="video-1", chapter_key="chapter-1", title="第一讲", duration=123, filename="")],
        ),
    )
