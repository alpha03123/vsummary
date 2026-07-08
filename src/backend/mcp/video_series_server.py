from __future__ import annotations

import os
from typing import Any

from backend.mcp.video_series_client import VideoSeriesBackendClient


class VideoSeriesTools:
    """Thin MCP tool wrapper around the local VSummary backend client."""

    def __init__(self, client: VideoSeriesBackendClient) -> None:
        self.client = client

    async def get_project_status(self, include_series: bool = True) -> dict[str, Any]:
        return await self.client.get_project_status(include_series=include_series)

    async def create_series(self, title: str) -> dict[str, Any]:
        return await self.client.create_series(title=title)

    async def add_series_videos(self, series_id: str, videos: list[dict[str, Any]]) -> dict[str, Any]:
        return await self.client.add_series_videos(series_id=series_id, videos=videos)

    async def process_series(
        self,
        series_id: str,
        video_ids: list[str] | None = None,
        run_id: str | None = None,
        transcript_enhancement_enabled: bool | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        return await self.client.process_series(
            series_id=series_id,
            video_ids=video_ids,
            run_id=run_id,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            wait=wait,
        )

    async def get_series_status(self, series_id: str, video_ids: list[str] | None = None) -> dict[str, Any]:
        return await self.client.get_series_status(series_id=series_id, video_ids=video_ids)

    async def export_series(
        self,
        series_id: str,
        kind: str = "mixed",
        video_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self.client.export_series(series_id=series_id, kind=kind, video_ids=video_ids)

    async def delete_series(self, series_id: str) -> dict[str, Any]:
        return await self.client.delete_series(series_id=series_id)


def create_mcp_server(client: VideoSeriesBackendClient | None = None):
    from mcp.server.fastmcp import FastMCP

    app = FastMCP("vsummary-video-series")
    backend_client = client or VideoSeriesBackendClient(
        base_url=os.environ.get("VSUMMARY_BACKEND_URL", "http://127.0.0.1:8000")
    )
    tools = VideoSeriesTools(backend_client)

    app.tool()(tools.get_project_status)
    app.tool()(tools.create_series)
    app.tool()(tools.add_series_videos)
    app.tool()(tools.process_series)
    app.tool()(tools.get_series_status)
    app.tool()(tools.export_series)
    app.tool()(tools.delete_series)
    return app


def main() -> None:
    create_mcp_server().run()


if __name__ == "__main__":
    main()
