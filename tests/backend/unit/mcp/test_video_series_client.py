from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
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

    async def test_import_local_series_uploads_file_paths_to_existing_import_api(self) -> None:
        seen_request: dict[str, str] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            body = request.read().decode("utf-8", errors="replace")
            seen_request["path"] = request.url.path
            seen_request["content_type"] = request.headers["content-type"]
            seen_request["body"] = body
            return httpx.Response(
                200,
                json={
                    "id": "audio-course",
                    "title": "Audio Course",
                    "videos": [{"id": "lesson-1", "title": "lesson-1", "source_type": "audio"}],
                    "is_linked": False,
                    "is_agent_managed": False,
                    "source_url": "",
                },
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            media_path = Path(temp_dir) / "lesson-1.mp3"
            media_path.write_bytes(b"audio")
            client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

            result = await client.import_local_series(title="Audio Course", file_paths=[str(media_path)])

        self.assertEqual("/api/import/local/series", seen_request["path"])
        self.assertIn("multipart/form-data", seen_request["content_type"])
        self.assertIn('name="series_title"', seen_request["body"])
        self.assertIn("Audio Course", seen_request["body"])
        self.assertIn('filename="lesson-1.mp3"', seen_request["body"])
        self.assertEqual("audio-course", result["series_id"])
        self.assertEqual("Audio Course", result["title"])
        self.assertEqual([{"id": "lesson-1", "title": "lesson-1", "source_type": "audio"}], result["videos"])

    async def test_add_local_series_videos_uploads_file_paths_to_existing_series_import_api(self) -> None:
        seen_request: dict[str, str] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            body = request.read().decode("utf-8", errors="replace")
            seen_request["path"] = request.url.raw_path.decode("ascii")
            seen_request["content_type"] = request.headers["content-type"]
            seen_request["body"] = body
            return httpx.Response(
                200,
                json=[{"id": "clip", "title": "clip", "source_type": "video"}],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            media_path = Path(temp_dir) / "clip.mp4"
            media_path.write_bytes(b"video")
            client = VideoSeriesBackendClient(transport=httpx.MockTransport(handler))

            result = await client.add_local_series_videos(series_id="agent/a", file_paths=[str(media_path)])

        self.assertEqual("/api/import/local/series/agent%2Fa", seen_request["path"])
        self.assertIn("multipart/form-data", seen_request["content_type"])
        self.assertIn('filename="clip.mp4"', seen_request["body"])
        self.assertEqual("agent/a", result["series_id"])
        self.assertEqual(1, result["added_count"])
        self.assertEqual([{"id": "clip", "title": "clip", "source_type": "video"}], result["videos"])

    async def test_import_local_series_rejects_missing_local_files_before_upload(self) -> None:
        client = VideoSeriesBackendClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))

        with self.assertRaisesRegex(FileNotFoundError, "local media file not found"):
            await client.import_local_series(title="Missing", file_paths=["missing.mp3"])

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

    async def test_export_series_writes_large_markdown_to_mcp_resource(self) -> None:
        large_markdown = "# One\n\n" + ("0123456789" * 700)

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/videos":
                return httpx.Response(
                    200,
                    json={
                        "series": [
                            {
                                "id": "agent-transformer",
                                "title": "Transformer 入门",
                                "videos": [{"id": "BV1", "title": "One", "processed": True, "is_linked": True}],
                            }
                        ],
                    },
                )
            if request.url.path == "/api/videos/agent-transformer/BV1/exports/mixed.md":
                return httpx.Response(200, text=large_markdown)
            return httpx.Response(404, json={"detail": "not found"})

        with tempfile.TemporaryDirectory() as temp_dir:
            client = VideoSeriesBackendClient(
                transport=httpx.MockTransport(handler),
                export_root=Path(temp_dir),
            )

            result = await client.export_series(series_id="agent-transformer", kind="mixed")

            self.assertEqual("resource", result["delivery"])
            self.assertEqual(1, result["exported_count"])
            self.assertGreater(result["markdown_chars"], result["inline_limit_chars"])
            self.assertTrue(result["truncated"])
            self.assertIn("preview", result)
            self.assertLessEqual(len(result["preview"]), result["preview_chars"])
            self.assertTrue(result["resource_uri"].startswith("vsummary://exports/"))
            self.assertEqual("resource_link", result["resource_link"]["type"])
            self.assertEqual(result["resource_uri"], result["resource_link"]["uri"])
            self.assertNotIn("markdown", result["items"][0])

            export_path = Path(result["output_path"])
            self.assertTrue(export_path.is_file())
            exported = client.read_export_resource(result["resource_date"], result["filename"])
            self.assertIn("# VSummary export: agent-transformer", exported)
            self.assertIn("<!-- video_id: BV1 -->", exported)
            self.assertIn(large_markdown, exported)

    async def test_export_series_force_file_writes_short_markdown_to_mcp_resource(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/videos":
                return httpx.Response(
                    200,
                    json={
                        "series": [
                            {
                                "id": "agent-transformer",
                                "title": "Transformer 入门",
                                "videos": [{"id": "BV1", "title": "One", "processed": True, "is_linked": True}],
                            }
                        ],
                    },
                )
            if request.url.path == "/api/videos/agent-transformer/BV1/exports/mixed.md":
                return httpx.Response(200, text="# One\n")
            return httpx.Response(404, json={"detail": "not found"})

        with tempfile.TemporaryDirectory() as temp_dir:
            client = VideoSeriesBackendClient(
                transport=httpx.MockTransport(handler),
                export_root=Path(temp_dir),
            )

            result = await client.export_series(series_id="agent-transformer", kind="mixed", force_file=True)

            self.assertEqual("resource", result["delivery"])
            self.assertEqual(1, result["exported_count"])
            self.assertFalse(result["truncated"])
            self.assertTrue(result["resource_uri"].startswith("vsummary://exports/"))
            self.assertNotIn("markdown", result["items"][0])
            self.assertEqual(len("# One\n"), result["items"][0]["markdown_chars"])
            self.assertTrue(Path(result["output_path"]).is_file())

    async def test_export_series_output_path_writes_short_markdown_to_requested_file(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/videos":
                return httpx.Response(
                    200,
                    json={
                        "series": [
                            {
                                "id": "agent-transformer",
                                "title": "Transformer 入门",
                                "videos": [{"id": "BV1", "title": "One", "processed": True, "is_linked": True}],
                            }
                        ],
                    },
                )
            if request.url.path == "/api/videos/agent-transformer/BV1/exports/mixed.md":
                return httpx.Response(200, text="# One\n")
            return httpx.Response(404, json={"detail": "not found"})

        with tempfile.TemporaryDirectory() as temp_dir:
            requested_path = Path(temp_dir) / "requested.md"
            client = VideoSeriesBackendClient(
                transport=httpx.MockTransport(handler),
                export_root=Path(temp_dir) / "exports",
            )

            result = await client.export_series(
                series_id="agent-transformer",
                kind="mixed",
                output_path=str(requested_path),
            )

            self.assertEqual("file", result["delivery"])
            self.assertEqual(str(requested_path), result["output_path"])
            self.assertEqual("", result["resource_uri"])
            self.assertNotIn("resource_link", result)
            self.assertTrue(requested_path.is_file())
            self.assertIn("# VSummary export: agent-transformer", requested_path.read_text(encoding="utf-8"))

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
