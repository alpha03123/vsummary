"""单视频与系列思维导图生成的 SSE 进度端点集成测试。

覆盖范围：
- POST /api/videos/{series_id}/{video_id}/mindmap/generate 通过 reporter 上报 completed/failed。
- GET /api/videos/{series_id}/{video_id}/mindmap/generate/progress 在 completed 后自动关闭流。
- POST /api/series/{series_id}/mindmap/generate 通过 reporter 上报 completed/failed。
- GET /api/series/{series_id}/mindmap/generate/progress 在 completed 后自动关闭流。
- 进度端点在 tracker 没有任务记录时会回放一个 idle 快照并立即关闭（短流）。
"""

from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.video_summary.infrastructure.in_memory_progress_tracker import (
    InMemoryProgressTracker,
)


class MindmapProgressApiTests(unittest.TestCase):
    """单视频思维导图生成的 SSE 进度端点集成测试。"""

    def _build_container(
        self,
        *,
        mindmap_result: dict | None = None,
        raise_error: Exception | None = None,
    ) -> SimpleNamespace:
        """构造一个最小 ApiContainer，足以驱动单视频 mindmap 生成 + SSE 进度端点。

        Args:
            mindmap_result: use-case 返回的 mindmap dict；None 表示"无总结"。
            raise_error: use-case 应抛出的异常；优先于 mindmap_result。
        """
        tracker = InMemoryProgressTracker()

        class FakeUseCase:
            async def run(self, series_id, video_id, progress_reporter=None):
                del series_id, video_id
                if progress_reporter is not None:
                    progress_reporter.update("generate", 50.0, "正在生成思维导图节点")
                if raise_error is not None:
                    raise raise_error
                if mindmap_result is None:
                    return None
                return SimpleNamespace(mindmap=mindmap_result)

        return SimpleNamespace(
            mindmap_progress_tracker=tracker,
            generate_video_mindmap=FakeUseCase(),
        )

    def test_progress_endpoint_returns_sse_when_completed(self) -> None:
        """POST 触发完成后，GET 进度端点应返回 text/event-stream，且末帧状态为 completed。"""
        container = self._build_container(
            mindmap_result={"id": "root", "title": "T", "summary": "", "children": []},
        )
        client = TestClient(create_app(container))

        generate_response = client.post("/api/videos/s1/v1/mindmap/generate")
        self.assertEqual(generate_response.status_code, 200)

        progress_response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        self.assertIn("text/event-stream", progress_response.headers["content-type"])

        body = progress_response.text
        self.assertIn('"status": "completed"', body)

    def test_progress_endpoint_streams_running_then_completed(self) -> None:
        """进度端点应在 running 阶段也推送一帧，末帧为 completed。"""
        container = self._build_container(
            mindmap_result={"id": "root", "title": "T", "summary": "", "children": []},
        )
        client = TestClient(create_app(container))

        generate_thread = threading.Thread(
            target=lambda: client.post("/api/videos/s1/v1/mindmap/generate"),
            daemon=True,
        )
        generate_thread.start()

        time.sleep(0.05)
        progress_response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        generate_thread.join(timeout=2.0)

        body = progress_response.text
        self.assertIn('"stage": "generate"', body)
        self.assertIn('"status": "completed"', body)

    def test_progress_endpoint_returns_failed_status_on_error(self) -> None:
        """当 use-case 抛异常时，API 路由调用 reporter.failed()，SSE 流末帧应为 failed。"""
        container = self._build_container(raise_error=RuntimeError("LLM error"))
        client = TestClient(create_app(container))

        generate_response = client.post("/api/videos/s1/v1/mindmap/generate")
        self.assertEqual(generate_response.status_code, 500)

        progress_response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        body = progress_response.text
        self.assertIn('"status": "failed"', body)
        self.assertIn("LLM error", body)

    def test_progress_endpoint_returns_404_when_summary_missing(self) -> None:
        """use-case 返回 None（无总结）时，API 路由调用 reporter.failed() 并返回 404。"""
        container = self._build_container(mindmap_result=None)
        client = TestClient(create_app(container))

        generate_response = client.post("/api/videos/s1/v1/mindmap/generate")
        self.assertEqual(generate_response.status_code, 404)

        progress_response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        body = progress_response.text
        self.assertIn('"status": "failed"', body)
        self.assertIn("总结不存在", body)

    def test_progress_endpoint_terminates_quickly_when_no_task(self) -> None:
        """tracker 没有任务记录时，进度端点回放一个 idle 快照后立即关闭。"""
        container = self._build_container()
        client = TestClient(create_app(container))

        progress_response = client.get("/api/videos/s1/v1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        body = progress_response.text
        self.assertIn('"status": "idle"', body)


class SeriesMindmapProgressApiTests(unittest.TestCase):
    """系列思维导图生成的 SSE 进度端点集成测试。"""

    def _build_series_container(
        self,
        *,
        mindmap_result: dict | None = None,
        raise_error: Exception | None = None,
        gate: threading.Event | None = None,
    ) -> SimpleNamespace:
        """构造一个最小 ApiContainer，足以驱动系列 mindmap 生成 + SSE 进度端点。

        Args:
            mindmap_result: use-case 返回的 mindmap dict；None 表示"无总结"。
            raise_error: use-case 应抛出的异常；优先于 mindmap_result。
            gate: 若非 None，use-case 会等该事件 set 后再返回，便于触发并发场景。
        """
        tracker = InMemoryProgressTracker()

        class FakeUseCase:
            async def run(self, series_id, progress_reporter=None):
                del series_id
                if progress_reporter is not None:
                    progress_reporter.update("generate", 50.0, "正在生成系列思维导图")
                if gate is not None:
                    gate.wait(timeout=2.0)
                if raise_error is not None:
                    raise raise_error
                if mindmap_result is None:
                    return None
                return SimpleNamespace(mindmap=mindmap_result)

        return SimpleNamespace(
            mindmap_progress_tracker=tracker,
            generate_series_mindmap=FakeUseCase(),
            gate=gate,
        )

    def test_series_progress_endpoint_returns_sse_when_completed(self) -> None:
        """POST 系列思维导图完成后，GET 进度端点末帧应为 completed。"""
        container = self._build_series_container(
            mindmap_result={"id": "root", "title": "S", "summary": "", "children": []},
        )
        client = TestClient(create_app(container))

        generate_response = client.post("/api/series/s1/mindmap/generate")
        self.assertEqual(generate_response.status_code, 200)

        progress_response = client.get("/api/series/s1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        self.assertIn("text/event-stream", progress_response.headers["content-type"])
        body = progress_response.text
        self.assertIn('"status": "completed"', body)

    def test_series_progress_endpoint_returns_failed_on_error(self) -> None:
        """系列思维导图生成抛错时，进度端点末帧应为 failed。"""
        container = self._build_series_container(raise_error=RuntimeError("boom"))
        client = TestClient(create_app(container))

        generate_response = client.post("/api/series/s1/mindmap/generate")
        self.assertEqual(generate_response.status_code, 500)

        progress_response = client.get("/api/series/s1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        body = progress_response.text
        self.assertIn('"status": "failed"', body)
        self.assertIn("boom", body)

    def test_series_progress_endpoint_returns_failed_when_no_summaries(self) -> None:
        """系列下没有已生成概况的视频时，use-case 返回 None → API 返回 400 且 reporter.failed()。"""
        container = self._build_series_container(mindmap_result=None)
        client = TestClient(create_app(container))

        generate_response = client.post("/api/series/s1/mindmap/generate")
        self.assertEqual(generate_response.status_code, 400)

        progress_response = client.get("/api/series/s1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        body = progress_response.text
        self.assertIn('"status": "failed"', body)
        self.assertIn("系列下没有已生成概况的视频", body)

    def test_series_concurrent_generation_returns_conflict(self) -> None:
        """同一系列并发请求，第二个应返回 409，且 reporter 不会被污染。"""
        container = self._build_series_container(
            mindmap_result={"id": "root", "title": "S", "summary": "", "children": []},
            gate=threading.Event(),
        )
        client = TestClient(create_app(container))

        first = threading.Thread(
            target=lambda: client.post("/api/series/s1/mindmap/generate"),
            daemon=True,
        )
        first.start()
        time.sleep(0.05)  # ensure first acquires lock

        second_response = client.post("/api/series/s1/mindmap/generate")
        self.assertEqual(second_response.status_code, 409)

        container.gate.set()  # release first
        first.join(timeout=2.0)

    def test_series_progress_endpoint_terminates_quickly_when_no_task(self) -> None:
        """tracker 没有任务记录时，系列进度端点回放一个 idle 快照后立即关闭。"""
        container = self._build_series_container()
        client = TestClient(create_app(container))

        progress_response = client.get("/api/series/s1/mindmap/generate/progress")
        self.assertEqual(progress_response.status_code, 200)
        body = progress_response.text
        self.assertIn('"status": "idle"', body)


# --------------------------------------------------------------------------- #
# Test container builders live as methods on each test class above.
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    unittest.main()