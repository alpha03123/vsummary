from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from tests._workspace_scope import attach_workspace_scope

from backend.local.http.app import create_app
from backend.bilibili.ytdlp_bilibili import BILIBILI_COOKIE_REQUIRED_MESSAGE
from backend.external.ytdlp import ExternalVideoResolutionError
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
                "kind": "standard",
            },
        )
        self.assertEqual(container.create_agent_series.calls, ["Transformer 入门"])

    def test_create_agent_series_rejects_blank_title(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/agent/series", json={"title": "   "})

        self.assertEqual(response.status_code, 422)

    def test_process_agent_series_submits_one_durable_job_per_pending_video(self) -> None:
        container = _build_container(videos=[
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
        ])
        client = TestClient(create_app(container))

        response = client.post("/api/agent/series/series-1/process", json={"video_ids": ["video-1", "video-2"]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "videos")
        self.assertEqual(response.json()["video_ids"], ["video-1", "video-2"])
        self.assertEqual([job["job_id"] for job in response.json()["jobs"]], ["job-1", "job-2"])
        self.assertEqual(
            container.job_repository.agent_submissions,
            [("video-1", "process_agent_video"), ("video-2", "process_agent_video")],
        )

    def test_process_agent_series_submits_all_pending_videos_when_not_explicitly_selected(self) -> None:
        container = _build_container()
        response = TestClient(create_app(container)).post("/api/agent/series/series-1/process", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["video_ids"], ["BV1xx411c7mD"])
        self.assertEqual(response.json()["jobs"][0]["job_id"], "job-1")

    def test_resolve_bilibili_video_returns_linked_video_card(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/linked/bilibili/resolve/video", json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "linked")
        self.assertTrue(payload["is_linked"])
        self.assertEqual(payload["source_id"], "BV1xx411c7mD")

    def test_init_bilibili_cookie_returns_configured_status(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/linked/bilibili/cookie/init")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True})
        self.assertTrue(container.bilibili_cookie_initializer.called)

    def test_resolve_youtube_video_uses_generic_provider_route(self) -> None:
        container = _build_container()

        async def resolve_video(*, provider, url, target_series_id):
            self.assertEqual(provider, "youtube")
            self.assertEqual(url, "https://www.youtube.com/watch?v=video_1")
            self.assertIsNone(target_series_id)
            return LibraryVideoCardDTO(
                id="video_1",
                title="YouTube 视频",
                source_name="video_1.mp4",
                processed=False,
                status="linked",
                is_linked=True,
                source_id="video_1",
                item_index=1,
                source_url=url,
                provider="youtube",
            )

        container.resolve_linked_video = SimpleNamespace(run=resolve_video)
        client = TestClient(create_app(container))

        response = client.post(
            "/api/linked/youtube/resolve/video",
            json={"url": "https://www.youtube.com/watch?v=video_1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "youtube")
        self.assertEqual(response.json()["source_id"], "video_1")

    def test_init_douyin_cookie_uses_provider_initializer(self) -> None:
        container = _build_container()
        initializer = _FakeBilibiliCookieInitializer()
        container.external_cookie_initializers = {"douyin": initializer}
        client = TestClient(create_app(container))

        response = client.post("/api/linked/douyin/cookie/init")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True})
        self.assertTrue(initializer.called)

    def test_douyin_cookie_requirement_returns_actionable_conflict(self) -> None:
        container = _build_container()

        async def resolve_video(*, provider, url, target_series_id):
            del provider, url, target_series_id
            raise ExternalVideoResolutionError("cookie_required", "test detail")

        container.resolve_linked_video = SimpleNamespace(run=resolve_video)
        client = TestClient(create_app(container))

        response = client.post(
            "/api/linked/douyin/resolve/video",
            json={"url": "https://www.douyin.com/video/7673754688373689615"},
        )

        self.assertEqual(response.status_code, 409)

    def test_bilibili_anti_spider_error_returns_cookie_message(self) -> None:
        async def resolve_series(url):
            del url
            raise RuntimeError("ERROR: [BiliBili] x: HTTP Error 412: Precondition Failed")

        client = TestClient(create_app(_build_container(resolve_series=resolve_series)))

        response = client.post("/api/linked/bilibili/resolve/series", json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], BILIBILI_COOKIE_REQUIRED_MESSAGE)

    def test_start_linked_video_download_submits_durable_job(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/BV1xx411c7mD/download")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], "job-1")
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(container.download_calls, [("series-1", "BV1xx411c7mD")])

    def test_cancel_linked_video_download_requests_durable_job_cancellation(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))
        client.post("/api/videos/series-1/BV1xx411c7mD/download")

        response = client.post("/api/videos/series-1/BV1xx411c7mD/download/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cancelled", "job_id": "job-1"})

    def test_cancel_series_generation_cancels_durable_parent_and_children(self) -> None:
        container = _build_container()
        container.job_repository.request_cancel_series_generation = lambda **_kwargs: [
            SimpleNamespace(id="series-job", resource_id="series-1", resource_type="series", operation="generate_series_batch", status="cancelled"),
            SimpleNamespace(id="video-job", resource_id="BV1xx411c7mD", resource_type="video", operation="generate_summary", status="cancelled"),
        ]

        response = TestClient(create_app(container)).post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "series-job")
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertEqual(response.json()["cancelled_video_ids"], ["BV1xx411c7mD"])
        self.assertEqual(response.json()["cancelled_job_ids"], ["series-job", "video-job"])

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
        source_id="BV1xx411c7mD",
        item_index=1,
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

    download_calls: list[tuple[str, str]] = []
    linked_workspace = _FakeLinkedWorkspace(video)
    job_repository = _FakeJobRepository(download_calls)

    container = attach_workspace_scope(SimpleNamespace(
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
        generate_series_summaries=_FakeGenerateSeriesSummaries(active_video_ids),
        generate_video_summary=_FakeGenerateVideoSummary(),
        generation_progress_tracker=generation_progress_tracker,
        video_download_progress_tracker=video_download_progress_tracker,
        linked_series_workspace=linked_workspace,
        job_repository=job_repository,
        download_calls=download_calls,
    ))
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
    async def run(self, series_id: str, video_id: str, *, transcript_enhancement_enabled=None, progress_reporter=None):
        del series_id, video_id, transcript_enhancement_enabled, progress_reporter
        await asyncio.sleep(0)


class _FakeLinkedWorkspace:
    def __init__(self, video: LibraryVideoCardDTO) -> None:
        self._video = video

    def get_linked_video_for_download(self, series_id: str, video_id: str):
        if series_id == "series-1" and video_id == self._video.id:
            return object()
        return None


class _FakeJobRepository:
    def __init__(self, download_calls: list[tuple[str, str]]) -> None:
        self._download_calls = download_calls
        self._jobs: dict[str, SimpleNamespace] = {}
        self.agent_submissions: list[tuple[str, str]] = []

    def submit(self, *, request_payload, **_kwargs):
        job_id = f"job-{len(self._jobs) + 1}"
        operation = _kwargs["operation"]
        if operation == "download_linked_video":
            self._download_calls.append((request_payload["series_id"], request_payload["video_id"]))
        if operation == "process_agent_video":
            self.agent_submissions.append((request_payload["video_id"], operation))
        self._jobs[job_id] = SimpleNamespace(id=job_id, status="queued", failure_detail=None)
        return SimpleNamespace(id=job_id, status="queued")

    def active_for_resource(self, *, resource_id, operation, **_kwargs):
        if operation != "download_linked_video":
            return None
        for snapshot in reversed(list(self._jobs.values())):
            if snapshot.status != "cancelled":
                return snapshot
        return None

    def request_cancel(self, job_id, **_kwargs):
        snapshot = self._jobs[job_id]
        snapshot.status = "cancelled"
        return snapshot

    def get(self, job_id, **_kwargs):
        snapshot = self._jobs.get(job_id)
        if snapshot is None or snapshot.status == "cancelled":
            return snapshot
        return SimpleNamespace(id=snapshot.id, status="succeeded", failure_detail=None)


if __name__ == "__main__":
    unittest.main()
