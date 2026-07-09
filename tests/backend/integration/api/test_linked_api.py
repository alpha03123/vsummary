from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


from backend.api.http.app import create_app
from backend.bilibili.ytdlp_bilibili import BILIBILI_COOKIE_REQUIRED_MESSAGE
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO


class LinkedApiTests(unittest.TestCase):
    def test_create_agent_series_returns_empty_linked_series(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/agent/series", json={"title": "  Transformer 入门  "})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": "agent-transformer",
                "title": "Transformer 入门",
                "videos": [],
                "is_linked": True,
                "is_agent_managed": True,
                "source_url": "",
            },
        )
        self.assertEqual(container.create_agent_series.calls, ["Transformer 入门"])

    def test_create_agent_series_rejects_blank_title(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/agent/series", json={"title": "   "})

        self.assertEqual(response.status_code, 422)

    def test_process_agent_series_schedules_existing_series_generation(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/agent/series/series-1/process", json={"run_id": "run-1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                "series_id": "series-1",
                "run_id": "run-1",
                "scope": "series",
                "video_ids": [],
                "status": "scheduled",
            },
            response.json(),
        )

    def test_process_agent_series_accepts_multiple_selected_videos(self) -> None:
        client = TestClient(create_app(_build_container(videos=[
            LibraryVideoCardDTO(
                id="video-1",
                title="视频 1",
                source_name="video-1.mp4",
                processed=False,
                status="pending",
            ),
            LibraryVideoCardDTO(
                id="video-2",
                title="视频 2",
                source_name="video-2.mp4",
                processed=False,
                status="pending",
            ),
        ])))

        response = client.post("/api/agent/series/series-1/process", json={"video_ids": ["video-1", "video-2"]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "videos")
        self.assertEqual(response.json()["video_ids"], ["video-1", "video-2"])

    def test_process_agent_series_downloads_linked_videos_before_generation(self) -> None:
        container = _build_container()

        async def run() -> None:
            await asyncio.wait_for(
                container.run_agent_series_generation(
                    container=container,
                    series_id="series-1",
                    run_id="run-1",
                    transcript_enhancement_enabled=None,
                ),
                timeout=1.0,
            )

        asyncio.run(run())

        self.assertEqual(container.download_calls, [("series-1", "BV1xx411c7mD")])
        self.assertEqual(container.generate_series_summaries.calls, [("series-1", "run-1")])

    def test_resolve_bilibili_video_returns_linked_video_card(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/linked/bilibili/resolve/video", json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "linked")
        self.assertTrue(payload["is_linked"])
        self.assertEqual(payload["bilibili_bvid"], "BV1xx411c7mD")

    def test_init_bilibili_cookie_returns_configured_status(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/linked/bilibili/cookie/init")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True})
        self.assertTrue(container.bilibili_cookie_initializer.called)

    def test_bilibili_anti_spider_error_returns_cookie_message(self) -> None:
        async def resolve_series(url):
            del url
            raise RuntimeError("ERROR: [BiliBili] x: HTTP Error 412: Precondition Failed")

        client = TestClient(create_app(_build_container(resolve_series=resolve_series)))

        response = client.post("/api/linked/bilibili/resolve/series", json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], BILIBILI_COOKIE_REQUIRED_MESSAGE)

    def test_start_linked_video_download_returns_task_id(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/videos/series-1/BV1xx411c7mD/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "started", "task_id": "download/series-1/BV1xx411c7mD"})

    def test_cancel_linked_video_download_marks_task_cancelling(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/BV1xx411c7mD/download/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cancelling"})
        snapshot = container.video_download_progress_tracker.get_snapshot("download/series-1/BV1xx411c7mD")
        self.assertEqual(snapshot.status, "cancelling")

    def test_cancel_series_generation_marks_active_video_and_linked_download_tasks(self) -> None:
        container = _build_container(
            active_video_ids=["local-video"],
            videos=[
                LibraryVideoCardDTO(
                    id="local-video",
                    title="本地视频",
                    source_name="local-video.mp4",
                    processed=False,
                    status="pending",
                ),
                LibraryVideoCardDTO(
                    id="BV1xx411c7mD",
                    title="外链视频",
                    source_name="BV1xx411c7mD.mp4",
                    processed=False,
                    status="linked",
                    is_linked=True,
                    bilibili_bvid="BV1xx411c7mD",
                    bilibili_page=1,
                    source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                ),
                LibraryVideoCardDTO(
                    id="ready-video",
                    title="已完成视频",
                    source_name="ready-video.mp4",
                    processed=True,
                    status="ready",
                ),
            ]
        )
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cancelled_video_ids"], ["local-video", "BV1xx411c7mD"])
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series/series-1").status, "cancelling")
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series-1/local-video").status, "cancelling")
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series-1/BV1xx411c7mD").status, "idle")
        self.assertEqual(
            container.video_download_progress_tracker.get_snapshot("download/series-1/BV1xx411c7mD").status,
            "cancelling",
        )
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series-1/ready-video").status, "idle")

    def test_cancel_series_generation_marks_series_cancelled_when_no_backend_series_task_is_active(self) -> None:
        container = _build_container(
            active_video_ids=[],
            videos=[
                LibraryVideoCardDTO(
                    id="BV1xx411c7mD",
                    title="外链视频",
                    source_name="BV1xx411c7mD.mp4",
                    processed=False,
                    status="linked",
                    is_linked=True,
                    bilibili_bvid="BV1xx411c7mD",
                    bilibili_page=1,
                    source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                ),
            ],
        )
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series/series-1").status, "cancelled")

    def test_mcp_streamable_http_endpoint_calls_existing_agent_series_api(self) -> None:
        container = _build_container()
        app = create_app(container)

        with TestClient(app, base_url="http://127.0.0.1:8001") as client:
            headers = {"accept": "application/json, text/event-stream"}
            response = client.post("/mcp", json=_mcp_initialize_payload(), headers=headers)
            self.assertEqual(response.status_code, 200)
            session_id = response.headers["mcp-session-id"]

            session_headers = {**headers, "mcp-session-id": session_id}
            initialized = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=session_headers,
            )
            self.assertEqual(initialized.status_code, 202)

            tools = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=session_headers,
            )
            tool_names = {
                tool["name"]
                for tool in _mcp_event_payload(tools.text)["result"]["tools"]
            }
            self.assertIn("create_series", tool_names)
            self.assertIn("process_series", tool_names)

            created = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "create_series", "arguments": {"title": "Agent 课程"}},
                },
                headers=session_headers,
            )

        result = _mcp_event_payload(created.text)["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(
            {
                "series_id": "agent-transformer",
                "title": "Agent 课程",
                "is_agent_managed": True,
                "videos": [],
            },
            result["structuredContent"],
        )
        self.assertEqual(container.create_agent_series.calls, ["Agent 课程"])

    def test_mcp_probe_get_without_session_returns_endpoint_metadata(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.get("/mcp")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                "status": "ok",
                "server": "vsummary-video-series",
                "transport": "streamable-http",
                "path": "/mcp",
            },
            response.json(),
        )

    def test_mcp_cleanup_delete_without_session_is_noop(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.delete("/mcp")

        self.assertEqual(response.status_code, 204)


def _build_container(
    videos: list[LibraryVideoCardDTO] | None = None,
    active_video_ids: list[str] | None = None,
    resolve_series=None,
):
    video = LibraryVideoCardDTO(
        id="BV1xx411c7mD",
        title="第一讲",
        source_name="BV1xx411c7mD.mp4",
        processed=False,
        status="linked",
        is_linked=True,
        bilibili_bvid="BV1xx411c7mD",
        bilibili_page=1,
        source_url="https://www.bilibili.com/video/BV1xx411c7mD",
    )
    resolved_videos = videos or [video]
    async def default_resolve_series(url):
        return LibrarySeriesDTO(id="series-1", title="课程", videos=resolved_videos, is_linked=True, source_url=url)

    async def resolve_video(url, target_series_id=None):
        del url, target_series_id
        return video

    generation_progress_tracker = InMemoryProgressTracker()
    video_download_progress_tracker = InMemoryProgressTracker()
    bilibili_cookie_initializer = _FakeBilibiliCookieInitializer()
    create_agent_series = _FakeCreateAgentSeries()

    def start_download(series_id, video_id):
        task_id = f"download/{series_id}/{video_id}"
        container.download_calls.append((series_id, video_id))
        video_download_progress_tracker.create_reporter(task_id).completed("下载完成")
        return SimpleNamespace(task_id=task_id)

    from backend.api.routes.linked import _run_agent_series_generation

    container = SimpleNamespace(
        root_dir=None,
        list_video_library=SimpleNamespace(
            run=lambda: SimpleNamespace(
                series=[
                    LibrarySeriesDTO(
                        id="series-1",
                        title="课程",
                        videos=resolved_videos,
                        is_linked=True,
                    )
                ]
            ),
        ),
        resolve_bilibili_series=SimpleNamespace(run=resolve_series or default_resolve_series),
        resolve_bilibili_video=SimpleNamespace(run=resolve_video),
        create_agent_series=create_agent_series,
        bilibili_cookie_initializer=bilibili_cookie_initializer,
        start_linked_video_download=SimpleNamespace(
            run=start_download,
        ),
        generate_series_summaries=_FakeGenerateSeriesSummaries(active_video_ids),
        generate_video_summary=_FakeGenerateVideoSummary(),
        generation_progress_tracker=generation_progress_tracker,
        video_download_progress_tracker=video_download_progress_tracker,
        download_calls=[],
        run_agent_series_generation=_run_agent_series_generation,
    )
    return container


def _mcp_initialize_payload() -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "vsummary-test", "version": "1"},
        },
    }


def _mcp_event_payload(response_text: str) -> dict[str, object]:
    for line in response_text.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError(f"MCP response did not contain an SSE data line: {response_text}")


class _FakeBilibiliCookieInitializer:
    def __init__(self) -> None:
        self.called = False

    def init(self) -> bool:
        self.called = True
        return True


class _FakeCreateAgentSeries:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, *, title: str) -> LibrarySeriesDTO:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("title cannot be blank")
        self.calls.append(normalized_title)
        return LibrarySeriesDTO(
            id="agent-transformer",
            title=normalized_title,
            videos=[],
            is_linked=True,
            is_agent_managed=True,
            source_url="",
        )


class _FakeGenerateSeriesSummaries:
    def __init__(self, active_video_ids: list[str] | None) -> None:
        self._active_video_ids = active_video_ids
        self.calls: list[tuple[str, str | None]] = []

    async def run(self, series_id: str, *, transcript_enhancement_enabled=None, run_id: str | None = None):
        del transcript_enhancement_enabled
        self.calls.append((series_id, run_id))
        await asyncio.sleep(0)

    def get_active_video_ids(self, series_id: str) -> list[str]:
        del series_id
        return self._active_video_ids if self._active_video_ids is not None else []


class _FakeGenerateVideoSummary:
    async def run(self, series_id: str, video_id: str, *, transcript_enhancement_enabled=None):
        del series_id, video_id, transcript_enhancement_enabled
        await asyncio.sleep(0)


if __name__ == "__main__":
    unittest.main()
