from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI

from backend.mcp.video_series_client import VideoSeriesBackendClient

MCP_SERVER_NAME = "vsummary-video-series"
MCP_HTTP_PATH = "/mcp"
MCP_INSTRUCTIONS = (
    "Use this server to operate VSummary video-series workflows. "
    "Create a series, add Bilibili URLs or local media file paths, process the series, poll status, "
    "then export Markdown text. Do not call raw VSummary HTTP APIs when MCP tools are available."
)


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

    async def import_local_series(self, title: str, file_paths: list[str]) -> dict[str, Any]:
        return await self.client.import_local_series(title=title, file_paths=file_paths)

    async def add_local_series_videos(self, series_id: str, file_paths: list[str]) -> dict[str, Any]:
        return await self.client.add_local_series_videos(series_id=series_id, file_paths=file_paths)

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

    app = FastMCP(MCP_SERVER_NAME, instructions=MCP_INSTRUCTIONS, streamable_http_path=MCP_HTTP_PATH)
    backend_client = client or VideoSeriesBackendClient(
        base_url=os.environ.get("VSUMMARY_BACKEND_URL", "http://127.0.0.1:8000")
    )
    tools = VideoSeriesTools(backend_client)

    app.tool()(tools.get_project_status)
    app.tool()(tools.create_series)
    app.tool()(tools.add_series_videos)
    app.tool()(tools.import_local_series)
    app.tool()(tools.add_local_series_videos)
    app.tool()(tools.process_series)
    app.tool()(tools.get_series_status)
    app.tool()(tools.export_series)
    app.tool()(tools.delete_series)
    return app


def install_mcp_http_endpoint(app: FastAPI) -> None:
    """Expose the VSummary MCP server as a Streamable HTTP endpoint on the FastAPI app."""
    backend_client = VideoSeriesBackendClient(
        base_url="http://vsummary.local",
        transport=httpx.ASGITransport(app=app),
    )
    mcp_server = create_mcp_server(client=backend_client)
    mcp_http_app = mcp_server.streamable_http_app()

    app.router.routes.extend(mcp_http_app.routes)
    app.state.mcp_server = mcp_server


def main() -> None:
    create_mcp_server().run()


if __name__ == "__main__":
    main()
