from __future__ import annotations

import importlib.util
import unittest
from inspect import signature
from pathlib import Path
from typing import Any

import httpx

from backend.mcp.video_series_client import BackendApiError, VideoSeriesBackendClient

_VERIFIER_PATH = Path(__file__).resolve().parents[4] / "scripts" / "verify_video_series_mcp.py"
_VERIFIER_SPEC = importlib.util.spec_from_file_location("verify_video_series_mcp", _VERIFIER_PATH)
assert _VERIFIER_SPEC is not None and _VERIFIER_SPEC.loader is not None
_VERIFIER_MODULE = importlib.util.module_from_spec(_VERIFIER_SPEC)
_VERIFIER_SPEC.loader.exec_module(_VERIFIER_MODULE)
redact_secrets = _VERIFIER_MODULE.redact_secrets


class VideoSeriesBackendClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_annotation_accepts_only_async_transport_or_none(self) -> None:
        annotation = signature(VideoSeriesBackendClient).parameters["transport"].annotation

        self.assertEqual("httpx.AsyncBaseTransport | None", annotation)

    async def test_health_check_calls_health_endpoint_and_adds_base_url(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            return httpx.Response(200, json={"status": "ok"})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.health_check()

        self.assertEqual(["/api/health"], seen_paths)
        self.assertEqual({"status": "ok", "base_url": "http://127.0.0.1:8000"}, result)

    async def test_create_series_rejects_blank_title_before_http(self) -> None:
        requested = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal requested
            requested = True
            return httpx.Response(200, json={})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        with self.assertRaises(ValueError):
            await client.create_series(title="  ")

        self.assertFalse(requested)

    async def test_add_series_videos_rejects_empty_videos_before_http(self) -> None:
        requested = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal requested
            requested = True
            return httpx.Response(200, json={})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        with self.assertRaises(ValueError):
            await client.add_series_videos(series_id="agent-a", videos=[])

        self.assertFalse(requested)

    async def test_add_series_videos_posts_payload_to_series_videos_endpoint(self) -> None:
        seen_requests: list[tuple[str, Any]] = []
        videos = [
            {"url": "https://www.bilibili.com/video/BV123", "title": "One", "source": "bilibili"}
        ]

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_requests.append((request.url.path, request.read()))
            return httpx.Response(200, json=[{"id": "BV123", "title": "One"}])

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.add_series_videos(series_id="agent-a", videos=videos)

        self.assertEqual([{"id": "BV123", "title": "One"}], result)
        self.assertEqual("/api/agent/series/agent-a/videos", seen_requests[0][0])
        self.assertEqual(b'{"videos":[{"url":"https://www.bilibili.com/video/BV123","title":"One","source":"bilibili"}]}', seen_requests[0][1])

    async def test_add_series_videos_encodes_series_id_as_single_path_segment(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.raw_path.decode("ascii"))
            return httpx.Response(200, json=[])

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        await client.add_series_videos(
            series_id="agent/a?b#c",
            videos=[{"url": "https://www.bilibili.com/video/BV123"}],
        )

        self.assertEqual(["/api/agent/series/agent%2Fa%3Fb%23c/videos"], seen_paths)

    async def test_process_series_posts_run_id_to_agent_process_endpoint(self) -> None:
        seen_requests: list[tuple[str, Any]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_requests.append((request.url.path, request.read()))
            return httpx.Response(200, json={"series_id": "agent-a", "run_id": "run-1", "status": "scheduled"})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.process_series(series_id="agent-a", run_id="run-1")

        self.assertEqual({"series_id": "agent-a", "run_id": "run-1", "status": "scheduled"}, result)
        self.assertEqual("/api/agent/series/agent-a/process", seen_requests[0][0])
        self.assertEqual(b'{"run_id":"run-1"}', seen_requests[0][1])

    async def test_process_series_encodes_series_id_as_single_path_segment(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.raw_path.decode("ascii"))
            return httpx.Response(200, json={})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        await client.process_series(series_id="agent/a?b#c", run_id="run-1")

        self.assertEqual(["/api/agent/series/agent%2Fa%3Fb%23c/process"], seen_paths)

    async def test_get_series_status_calls_agent_status_endpoint(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            return httpx.Response(
                200,
                json={
                    "id": "agent-b",
                    "title": "B",
                    "videos": [
                        {
                            "id": "BV123",
                            "title": "One",
                            "status": "ready",
                            "processed": True,
                            "is_linked": True,
                            "source_url": "https://www.bilibili.com/video/BV123",
                            "artifacts": {"summary": True, "transcript": False},
                            "failure_reason": "",
                        }
                    ],
                },
            )

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.get_series_status(series_id="agent-b")

        self.assertEqual(["/api/agent/series/agent-b/status"], seen_paths)
        self.assertEqual(
            {
                "id": "agent-b",
                "title": "B",
                "videos": [
                    {
                        "id": "BV123",
                        "title": "One",
                        "status": "ready",
                        "processed": True,
                        "is_linked": True,
                        "source_url": "https://www.bilibili.com/video/BV123",
                        "artifacts": {"summary": True, "transcript": False},
                        "failure_reason": "",
                    }
                ],
            },
            result,
        )

    async def test_get_series_status_encodes_series_id_as_single_path_segment(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.raw_path.decode("ascii"))
            return httpx.Response(200, json={"id": "agent/a?b#c", "title": "A", "videos": []})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        await client.get_series_status(series_id="agent/a?b#c")

        self.assertEqual(["/api/agent/series/agent%2Fa%3Fb%23c/status"], seen_paths)

    async def test_export_series_markdown_posts_to_export_endpoint(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            return httpx.Response(200, json={"output_dir": "D:/exports/A", "exported_count": 2})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.export_series_markdown(series_id="agent-a")

        self.assertEqual(["/api/series/agent-a/exports/markdown"], seen_paths)
        self.assertEqual({"output_dir": "D:/exports/A", "exported_count": 2}, result)

    async def test_export_series_markdown_encodes_series_id_as_single_path_segment(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.raw_path.decode("ascii"))
            return httpx.Response(200, json={})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        await client.export_series_markdown(series_id="agent/a?b#c")

        self.assertEqual(["/api/series/agent%2Fa%3Fb%23c/exports/markdown"], seen_paths)

    async def test_series_methods_reject_blank_series_id_before_http(self) -> None:
        requested = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal requested
            requested = True
            return httpx.Response(200, json={})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        with self.assertRaises(ValueError):
            await client.add_series_videos(
                series_id=" ",
                videos=[{"url": "https://www.bilibili.com/video/BV123"}],
            )
        with self.assertRaises(ValueError):
            await client.process_series(series_id=" ")
        with self.assertRaises(ValueError):
            await client.get_series_status(series_id=" ")
        with self.assertRaises(ValueError):
            await client.export_series_markdown(series_id=" ")

        self.assertFalse(requested)

    async def test_add_series_videos_rejects_obviously_invalid_urls_before_http(self) -> None:
        requested = False

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal requested
            requested = True
            return httpx.Response(200, json=[])

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        for url in ["", "ftp://example.com/video/BV123", "not-a-url", "https://www.bilibili.com"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                await client.add_series_videos(series_id="agent-a", videos=[{"url": url}])

        self.assertFalse(requested)

    async def test_backend_error_includes_status_code_and_detail(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"detail": "Bilibili Cookie required"})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        with self.assertRaises(BackendApiError) as raised:
            await client.create_series(title="Agent Series")

        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual("Bilibili Cookie required", raised.exception.detail)
        self.assertIn("409", str(raised.exception))
        self.assertIn("Bilibili Cookie required", str(raised.exception))

    async def test_get_project_status_never_exposes_cookie_values(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/api/get_downloader_cookie/bilibili":
                return httpx.Response(
                    200,
                    json={
                        "platform": "bilibili",
                        "configured": True,
                        "cookie": "SESSDATA=secret",
                        "SESSDATA": "secret",
                    },
                )
            return httpx.Response(404, json={"detail": "not found"})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.get_project_status()

        self.assertEqual(
            {
                "health": {"status": "ok", "base_url": "http://127.0.0.1:8000"},
                "bilibili_cookie_configured": True,
            },
            result,
        )
        self.assertNotIn("secret", repr(result))
        self.assertNotIn("SESSDATA", repr(result))

    async def test_verifier_redaction_keeps_bilibili_cookie_configured_boolean(self) -> None:
        result = redact_secrets(
            {
                "bilibili_cookie_configured": True,
                "cookie": "SESSDATA=secret",
                "bili_jct": "csrf-secret",
                "message": "token=secret",
            }
        )

        self.assertEqual(True, result["bilibili_cookie_configured"])
        self.assertEqual("[redacted]", result["cookie"])
        self.assertEqual("[redacted]", result["bili_jct"])
        self.assertEqual("token=[redacted]", result["message"])


if __name__ == "__main__":
    unittest.main()
