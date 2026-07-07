from __future__ import annotations

import os
from typing import Any

from backend.mcp.video_series_client import VideoSeriesBackendClient


class VideoSeriesTools:
    """Thin MCP tool wrapper around a video series backend client."""

    def __init__(self, client: VideoSeriesBackendClient) -> None:
        self.client = client

    async def health_check(self) -> dict[str, Any]:
        return await self.client.health_check()

    async def get_project_status(self) -> dict[str, Any]:
        return await self.client.get_project_status()

    async def create_series(self, title: str, source: str = "agent", notes: str = "") -> dict[str, Any]:
        return await self.client.create_series(title=title, source=source, notes=notes)

    async def add_series_videos(self, series_id: str, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self.client.add_series_videos(series_id=series_id, videos=videos)

    async def process_series(self, series_id: str, run_id: str | None = None) -> dict[str, Any]:
        return await self.client.process_series(series_id=series_id, run_id=run_id)

    async def get_series_status(self, series_id: str) -> dict[str, Any]:
        return await self.client.get_series_status(series_id=series_id)

    async def export_series_markdown(self, series_id: str) -> dict[str, Any]:
        return await self.client.export_series_markdown(series_id=series_id)


def create_mcp_server(client: VideoSeriesBackendClient | None = None):
    from mcp.server.fastmcp import FastMCP

    app = FastMCP("vsummary-video-series")
    backend_client = client or VideoSeriesBackendClient(
        base_url=os.environ.get("VSUMMARY_BACKEND_URL", "http://127.0.0.1:8000")
    )
    tools = VideoSeriesTools(backend_client)

    app.tool()(tools.health_check)
    app.tool()(tools.get_project_status)
    app.tool()(tools.create_series)
    app.tool()(tools.add_series_videos)
    app.tool()(tools.process_series)
    app.tool()(tools.get_series_status)
    app.tool()(tools.export_series_markdown)

    return app


def main() -> None:
    create_mcp_server().run()


if __name__ == "__main__":
    main()
