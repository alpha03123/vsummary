from __future__ import annotations

import unittest
import time
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.chaoxing.chaoxing_api import ChaoxingInitCancelled
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


class ChaoxingApiTests(unittest.TestCase):
    def test_status_reports_initialization_state(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.get("/api/linked/chaoxing/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"initialized": True})

    def test_status_returns_clear_error_when_dependency_is_missing(self) -> None:
        container = _build_container()
        container.chaoxing_importer.is_initialized = lambda: (_ for _ in ()).throw(
            RuntimeError("当前 Python 环境缺少 chaoxing-downloader 包，请先安装项目依赖。")
        )
        client = TestClient(create_app(container))

        response = client.get("/api/linked/chaoxing/status")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "当前 Python 环境缺少 chaoxing-downloader 包，请先安装项目依赖。")

    def test_import_course_starts_background_task_and_saves_linked_series(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/linked/chaoxing/import/course", json={"course_key": "course-1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["task_id"].startswith("chaoxing-import-"))
        self.assertEqual(payload["series_id"], "chaoxing-course-1")
        snapshot = _wait_for_import_completion(container, payload["task_id"])
        self.assertEqual(snapshot.status, "completed")
        self.assertEqual(container.saved_series.series_id, "chaoxing-course-1")
        self.assertEqual(container.invalidate_calls, 1)

    def test_cancel_import_course_stops_background_save(self) -> None:
        container = _build_container()
        import_started = Event()
        release_import = Event()

        def import_course(course_key, progress=None):
            del course_key
            if progress is not None:
                progress.update("import", 50.0, "正在解析视频章节 1/1")
            import_started.set()
            release_import.wait(timeout=1.0)
            return container.sample_series

        container.chaoxing_importer.import_course = import_course
        client = TestClient(create_app(container))

        response = client.post("/api/linked/chaoxing/import/course", json={"course_key": "course-1"})
        payload = response.json()
        self.assertTrue(import_started.wait(timeout=1.0))

        cancel_response = client.post(f"/api/linked/chaoxing/import/course/{payload['task_id']}/cancel")
        release_import.set()
        snapshot = _wait_for_import_completion(container, payload["task_id"])

        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json(), {"status": "cancelling", "task_id": payload["task_id"]})
        self.assertEqual(snapshot.status, "cancelled")
        self.assertIsNone(container.saved_series)
        self.assertEqual(container.invalidate_calls, 0)

    def test_init_returns_conflict_when_login_is_cancelled(self) -> None:
        container = _build_container()
        container.chaoxing_importer.init = lambda: (_ for _ in ()).throw(ChaoxingInitCancelled("超星初始化已中断"))
        client = TestClient(create_app(container))

        response = client.post("/api/linked/chaoxing/init")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "超星初始化已中断")

    def test_cancel_init_delegates_to_importer(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/linked/chaoxing/init/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cancelled"})
        self.assertEqual(container.cancel_init_calls, 1)


def _build_container():
    video = LinkedVideo(
        bvid="chaoxing-video-1",
        page=1,
        title="第一讲",
        cover_url="",
        duration_seconds=123,
        source_url="chaoxing://video/video-1",
        provider="chaoxing",
        download_key="video-1",
    )
    series = LinkedSeries(
        series_id="chaoxing-course-1",
        title="超星课程",
        cover_url="",
        source_url="chaoxing://course/course-1",
        videos=[video],
    )
    container = SimpleNamespace(
        root_dir=None,
        chaoxing_importer=SimpleNamespace(
            is_initialized=lambda: True,
            init=lambda: None,
            list_courses=lambda: [SimpleNamespace(course_key="course-1", title="超星课程", teacher="老师", open_time="")],
            list_chapters=lambda course_key: [SimpleNamespace(chapter_key="chapter-1", title="第一章", order="1")],
            list_videos=lambda chapter_key: [SimpleNamespace(video_key="video-1", chapter_key=chapter_key, title="第一讲", duration=123, filename="")],
            import_course=lambda course_key, progress=None: _import_course(series, progress),
        ),
        video_download_progress_tracker=InMemoryProgressTracker(),
        chaoxing_import_progress_tracker=InMemoryProgressTracker(),
    )
    container.saved_series = None
    container.sample_series = series
    container.invalidate_calls = 0
    container.cancel_init_calls = 0
    container.chaoxing_importer.cancel_init = lambda: setattr(container, "cancel_init_calls", container.cancel_init_calls + 1)
    container.linked_series_workspace = SimpleNamespace(
        save_linked_series=lambda linked_series: setattr(container, "saved_series", linked_series),
    )
    container.workspace_index_invalidator = SimpleNamespace(
        invalidate=lambda: setattr(container, "invalidate_calls", container.invalidate_calls + 1),
    )
    return container


def _import_course(series, progress=None):
    if progress is not None:
        progress.update("import", 50.0, "正在解析视频章节 1/1")
    return series


def _wait_for_import_completion(container, task_id: str):
    deadline = time.time() + 2.0
    while time.time() < deadline:
        snapshot = container.chaoxing_import_progress_tracker.get_snapshot(task_id)
        if snapshot.status in {"completed", "failed"}:
            return snapshot
        time.sleep(0.05)
    return container.chaoxing_import_progress_tracker.get_snapshot(task_id)


if __name__ == "__main__":
    unittest.main()
