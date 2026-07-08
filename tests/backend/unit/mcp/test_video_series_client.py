from __future__ import annotations

import unittest
import json
from typing import Any

import httpx

from backend.mcp.video_series_client import VideoSeriesBackendClient, _overall_status


class VideoSeriesBackendClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_project_status_returns_health_and_series_summary(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path == "/api/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/api/videos":
                return httpx.Response(
                    200,
                    json={
                        "workspace": {"id": "workspace", "title": "Workspace"},
                        "series": [
                            {
                                "id": "agent-transformer",
                                "title": "Transformer 入门",
                                "is_linked": True,
                                "is_agent_managed": True,
                                "source_url": "",
                                "videos": [
                                    {"id": "BV1", "title": "One", "processed": True, "is_linked": True},
                                    {"id": "BV2", "title": "Two", "processed": False, "is_linked": True},
                                ],
                            }
                        ],
                    },
                )
            return httpx.Response(404, json={"detail": "not found"})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.get_project_status()

        self.assertEqual(["/api/health", "/api/videos"], seen_paths)
        self.assertEqual("ok", result["backend"]["status"])
        self.assertEqual("unknown", result["bilibili"]["cookie_configured"])
        self.assertEqual(
            {
                "id": "agent-transformer",
                "title": "Transformer 入门",
                "video_count": 2,
                "processed_count": 1,
                "linked_count": 2,
                "is_agent_managed": True,
            },
            result["series"][0],
        )

    async def test_create_series_posts_to_agent_series_api(self) -> None:
        seen_requests: list[tuple[str, bytes]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_requests.append((request.url.path, request.read()))
            return httpx.Response(
                200,
                json={
                    "id": "agent-transformer",
                    "title": "Transformer 入门",
                    "videos": [],
                    "is_linked": True,
                    "is_agent_managed": True,
                    "source_url": "",
                },
            )

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.create_series(title="Transformer 入门")

        self.assertEqual("/api/agent/series", seen_requests[0][0])
        self.assertEqual(
            {"series_id": "agent-transformer", "title": "Transformer 入门", "is_agent_managed": True, "videos": []},
            result,
        )

    async def test_add_series_videos_uses_existing_single_video_resolve_api(self) -> None:
        seen_payloads: list[Any] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.read().decode("utf-8"))
            seen_payloads.append(payload)
            return httpx.Response(
                200,
                json={
                    "id": payload["url"].rstrip("/").split("/")[-1],
                    "title": "Resolved",
                    "source_name": "source.mp4",
                    "source_type": "video",
                    "processed": False,
                    "status": "linked",
                    "is_linked": True,
                },
            )

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.add_series_videos(
            series_id="agent-transformer",
            videos=[
                {"url": "https://www.bilibili.com/video/BV1"},
                {"url": "https://www.bilibili.com/video/BV2"},
            ],
        )

        self.assertEqual(
            [
                {"url": "https://www.bilibili.com/video/BV1", "target_series_id": "agent-transformer"},
                {"url": "https://www.bilibili.com/video/BV2", "target_series_id": "agent-transformer"},
            ],
            seen_payloads,
        )
        self.assertEqual(2, result["added_count"])
        self.assertEqual(0, result["failed_count"])
        self.assertEqual(["BV1", "BV2"], [item["video_id"] for item in result["items"]])

    async def test_process_series_starts_background_agent_process(self) -> None:
        seen_requests: list[tuple[str, bytes]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_requests.append((request.url.raw_path.decode("ascii"), request.read()))
            return httpx.Response(
                200,
                json={
                    "series_id": "agent/a",
                    "run_id": "run-1",
                    "scope": "series",
                    "video_ids": [],
                    "status": "scheduled",
                },
            )

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.process_series(series_id="agent/a", run_id="run-1")

        self.assertEqual("/api/agent/series/agent%2Fa/process", seen_requests[0][0])
        self.assertEqual("scheduled", result["status"])
        self.assertEqual("run-1", result["run_id"])

    async def test_export_series_returns_markdown_for_each_video(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/videos":
                return httpx.Response(
                    200,
                    json={
                        "workspace": {"id": "workspace", "title": "Workspace"},
                        "series": [
                            {
                                "id": "agent-transformer",
                                "title": "Transformer 入门",
                                "is_linked": True,
                                "is_agent_managed": True,
                                "source_url": "",
                                "videos": [
                                    {"id": "BV1", "title": "One", "processed": True, "is_linked": True},
                                    {"id": "BV2", "title": "Two", "processed": False, "is_linked": True},
                                ],
                            }
                        ],
                    },
                )
            if request.url.path == "/api/videos/agent-transformer/BV1/exports/mixed.md":
                return httpx.Response(200, text="# One\n")
            if request.url.path == "/api/videos/agent-transformer/BV2/exports/mixed.md":
                return httpx.Response(404, json={"detail": "summary not found"})
            return httpx.Response(404, json={"detail": "not found"})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.export_series(series_id="agent-transformer", kind="mixed")

        self.assertEqual(1, result["exported_count"])
        self.assertEqual(1, result["failed_count"])
        self.assertEqual("exported", result["items"][0]["status"])
        self.assertEqual("# One\n", result["items"][0]["markdown"])
        self.assertEqual("missing", result["items"][1]["status"])

    async def test_delete_series_uses_existing_backend_delete_api(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.raw_path.decode("ascii"))
            return httpx.Response(200, json={"status": "deleted", "series_id": "agent/a"})

        client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

        result = await client.delete_series("agent/a")

        self.assertEqual(["/api/series/agent%2Fa"], seen_paths)
        self.assertEqual({"status": "deleted", "series_id": "agent/a"}, result)


class VideoSeriesStatusAggregationTests(unittest.TestCase):
    def test_overall_status_does_not_report_completed_while_videos_are_still_running(self) -> None:
        status = _overall_status(
            {"snapshot": {"status": "completed"}},
            [
                {
                    "processed": False,
                    "generation": {"status": "running"},
                }
            ],
        )

        self.assertEqual("processing", status)

    def test_overall_status_reports_completed_only_when_all_videos_are_processed(self) -> None:
        status = _overall_status(
            {"snapshot": {"status": "completed"}},
            [
                {
                    "processed": True,
                    "generation": {"status": "completed"},
                }
            ],
        )

        self.assertEqual("completed", status)


if __name__ == "__main__":
    unittest.main()
