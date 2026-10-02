from __future__ import annotations

import importlib.util
import unittest
from typing import Any

from backend.mcp.video_series_server import create_mcp_server


class FakeVideoSeriesClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_project_status(self, include_series: bool = True) -> dict[str, Any]:
        self.calls.append(("get_project_status", {"include_series": include_series}))
        return {"backend": {"status": "ok"}}

    async def create_series(self, title: str) -> dict[str, Any]:
        self.calls.append(("create_series", {"title": title}))
        return {"series_id": "agent-transformer", "title": title, "is_agent_managed": True, "videos": []}

    async def add_series_videos(self, series_id: str, videos: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(("add_series_videos", {"series_id": series_id, "videos": videos}))
        return {"added_count": len(videos), "failed_count": 0, "items": []}

    async def import_local_series(self, title: str, file_paths: list[str]) -> dict[str, Any]:
        self.calls.append(("import_local_series", {"title": title, "file_paths": file_paths}))
        return {"series_id": "audio-course", "title": title, "videos": []}

    async def add_local_series_videos(self, series_id: str, file_paths: list[str]) -> dict[str, Any]:
        self.calls.append(("add_local_series_videos", {"series_id": series_id, "file_paths": file_paths}))
        return {"series_id": series_id, "added_count": len(file_paths), "videos": []}

    async def process_series(
        self,
        series_id: str,
        video_ids: list[str] | None = None,
        run_id: str | None = None,
        transcript_enhancement_enabled: bool | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "process_series",
                {
                    "series_id": series_id,
                    "video_ids": video_ids,
                    "run_id": run_id,
                    "transcript_enhancement_enabled": transcript_enhancement_enabled,
                    "wait": wait,
                },
            )
        )
        return {"status": "scheduled", "series_id": series_id}

    async def get_series_status(self, series_id: str, video_ids: list[str] | None = None) -> dict[str, Any]:
        self.calls.append(("get_series_status", {"series_id": series_id, "video_ids": video_ids}))
        return {"series_id": series_id, "videos": []}

    async def export_series(
        self,
        series_id: str,
        kind: str = "mixed",
        video_ids: list[str] | None = None,
        force_file: bool = False,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "export_series",
                {
                    "series_id": series_id,
                    "kind": kind,
                    "video_ids": video_ids,
                    "force_file": force_file,
                    "output_path": output_path,
                },
            )
        )
        return {"series_id": series_id, "kind": kind, "items": []}

    def read_export_resource(self, date: str, filename: str) -> str:
        self.calls.append(("read_export_resource", {"date": date, "filename": filename}))
        return "# Export\n"

    async def delete_series(self, series_id: str) -> dict[str, Any]:
        self.calls.append(("delete_series", {"series_id": series_id}))
        return {"status": "deleted", "series_id": series_id}


@unittest.skipIf(importlib.util.find_spec("mcp") is None, "mcp package is not installed")
class VideoSeriesServerRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_mcp_server_registers_expected_tools(self) -> None:
        app = create_mcp_server(client=FakeVideoSeriesClient())

        tools = await app.list_tools()

        self.assertEqual(
            {
                "get_project_status",
                "create_series",
                "add_series_videos",
                "import_local_series",
                "add_local_series_videos",
                "process_series",
                "get_series_status",
                "export_series",
                "delete_series",
            },
            {tool.name for tool in tools},
        )

    async def test_create_mcp_server_registers_export_resource_template(self) -> None:
        client = FakeVideoSeriesClient()
        app = create_mcp_server(client=client)

        resources = await app.read_resource("vsummary://exports/2026-07-09/export.md")

        self.assertEqual("# Export\n", resources[0].content)
        self.assertEqual("text/markdown", resources[0].mime_type)
        self.assertEqual(("read_export_resource", {"date": "2026-07-09", "filename": "export.md"}), client.calls[-1])


if __name__ == "__main__":
    unittest.main()
