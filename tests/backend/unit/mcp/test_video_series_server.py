from __future__ import annotations

import unittest
import asyncio
from typing import Any

from backend.mcp.video_series_server import VideoSeriesTools, create_mcp_server


class FakeVideoSeriesClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def health_check(self) -> dict[str, Any]:
        self.calls.append(("health_check", (), {}))
        return {"status": "ok"}

    async def get_project_status(self) -> dict[str, Any]:
        self.calls.append(("get_project_status", (), {}))
        return {"bilibili_cookie_configured": True}

    async def create_series(self, title: str, source: str = "agent", notes: str = "") -> dict[str, Any]:
        self.calls.append(("create_series", (), {"title": title, "source": source, "notes": notes}))
        return {"id": "agent-series", "title": title, "source": source, "notes": notes}

    async def add_series_videos(self, series_id: str, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.calls.append(("add_series_videos", (), {"series_id": series_id, "videos": videos}))
        return [{"id": "BV123", "title": "One"}]

    async def process_series(self, series_id: str, run_id: str | None = None) -> dict[str, Any]:
        self.calls.append(("process_series", (), {"series_id": series_id, "run_id": run_id}))
        return {"series_id": series_id, "run_id": run_id, "status": "started"}

    async def get_series_status(self, series_id: str) -> dict[str, Any]:
        self.calls.append(("get_series_status", (), {"series_id": series_id}))
        return {"id": series_id, "videos": []}

    async def export_series_markdown(self, series_id: str) -> dict[str, Any]:
        self.calls.append(("export_series_markdown", (), {"series_id": series_id}))
        return {"output_dir": "D:/exports/agent-series", "exported_count": 2}


class VideoSeriesToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_series_delegates_title_source_and_notes(self) -> None:
        client = FakeVideoSeriesClient()
        tools = VideoSeriesTools(client)

        result = await tools.create_series(title="Agent Course", source="web", notes="selected manually")

        self.assertEqual(
            {"id": "agent-series", "title": "Agent Course", "source": "web", "notes": "selected manually"},
            result,
        )
        self.assertEqual(
            [("create_series", (), {"title": "Agent Course", "source": "web", "notes": "selected manually"})],
            client.calls,
        )

    async def test_add_series_videos_delegates_candidate_list_unchanged(self) -> None:
        client = FakeVideoSeriesClient()
        tools = VideoSeriesTools(client)
        videos = [
            {"url": "https://www.bilibili.com/video/BV123", "title": "One", "source": "bilibili"},
            {"url": "https://www.bilibili.com/video/BV456", "title": "Two", "source": "bilibili"},
        ]

        result = await tools.add_series_videos(series_id="agent-series", videos=videos)

        self.assertEqual([{"id": "BV123", "title": "One"}], result)
        self.assertIs(videos, client.calls[0][2]["videos"])
        self.assertEqual("agent-series", client.calls[0][2]["series_id"])

    async def test_export_series_markdown_returns_client_output_dir_and_count(self) -> None:
        client = FakeVideoSeriesClient()
        tools = VideoSeriesTools(client)

        result = await tools.export_series_markdown(series_id="agent-series")

        self.assertEqual({"output_dir": "D:/exports/agent-series", "exported_count": 2}, result)
        self.assertEqual(
            [("export_series_markdown", (), {"series_id": "agent-series"})],
            client.calls,
        )

    async def test_health_project_process_and_status_delegate_to_client(self) -> None:
        client = FakeVideoSeriesClient()
        tools = VideoSeriesTools(client)

        self.assertEqual({"status": "ok"}, await tools.health_check())
        self.assertEqual({"bilibili_cookie_configured": True}, await tools.get_project_status())
        self.assertEqual(
            {"series_id": "agent-series", "run_id": "run-1", "status": "started"},
            await tools.process_series(series_id="agent-series", run_id="run-1"),
        )
        self.assertEqual({"id": "agent-series", "videos": []}, await tools.get_series_status(series_id="agent-series"))
        self.assertEqual(
            [
                ("health_check", (), {}),
                ("get_project_status", (), {}),
                ("process_series", (), {"series_id": "agent-series", "run_id": "run-1"}),
                ("get_series_status", (), {"series_id": "agent-series"}),
            ],
            client.calls,
        )

    async def test_create_mcp_server_registers_expected_tool_names(self) -> None:
        asyncio.get_running_loop().slow_callback_duration = 1.0
        app = create_mcp_server(client=FakeVideoSeriesClient())

        tools = await app.list_tools()

        self.assertEqual(
            {
                "health_check",
                "get_project_status",
                "create_series",
                "add_series_videos",
                "process_series",
                "get_series_status",
                "export_series_markdown",
            },
            {tool.name for tool in tools},
        )


if __name__ == "__main__":
    unittest.main()
