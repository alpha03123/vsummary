from __future__ import annotations

from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import httpx


class BackendApiError(RuntimeError):
    """Error returned by the local backend API."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Backend API error {status_code}: {detail}")


class VideoSeriesBackendClient:
    """HTTP client used by MCP tools to call the local backend."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def health_check(self) -> dict[str, Any]:
        health = await self._request("GET", "/api/health")
        health["base_url"] = self.base_url
        return health

    async def get_project_status(self) -> dict[str, Any]:
        health = await self.health_check()
        cookie_status = await self._request("GET", "/api/get_downloader_cookie/bilibili")
        return {
            "health": health,
            "bilibili_cookie_configured": bool(cookie_status.get("configured")),
        }

    async def create_series(self, title: str, source: str = "agent", notes: str = "") -> dict[str, Any]:
        if not title.strip():
            raise ValueError("title must not be blank")
        return await self._request(
            "POST",
            "/api/agent/series",
            json={"title": title, "source": source, "notes": notes},
        )

    async def add_series_videos(self, series_id: str, videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not series_id.strip():
            raise ValueError("series_id must not be blank")
        if not videos:
            raise ValueError("videos must not be empty")
        for video in videos:
            self._validate_video_url(video.get("url", ""))
        result = await self._request(
            "POST",
            f"/api/agent/series/{self._path_segment(series_id)}/videos",
            json={"videos": videos},
        )
        if not isinstance(result, list):
            raise BackendApiError(502, "backend returned non-list response for series videos")
        return result

    async def process_series(self, series_id: str, run_id: str | None = None) -> dict[str, Any]:
        if not series_id.strip():
            raise ValueError("series_id must not be blank")
        return await self._request(
            "POST",
            f"/api/agent/series/{self._path_segment(series_id)}/process",
            json={"run_id": run_id},
        )

    async def get_series_status(self, series_id: str) -> dict[str, Any]:
        if not series_id.strip():
            raise ValueError("series_id must not be blank")
        return await self._request("GET", f"/api/agent/series/{self._path_segment(series_id)}/status")

    async def export_series_markdown(self, series_id: str) -> dict[str, Any]:
        if not series_id.strip():
            raise ValueError("series_id must not be blank")
        return await self._request("POST", f"/api/series/{self._path_segment(series_id)}/exports/markdown")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.request(method, path, **kwargs)

        if response.status_code >= 400:
            raise BackendApiError(response.status_code, self._error_detail(response))

        if not response.content:
            return {}
        return response.json()

    def _error_detail(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text
        detail = body.get("detail") if isinstance(body, dict) else None
        return str(detail if detail is not None else body)

    def _validate_video_url(self, url: object) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("video url must not be blank")
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path:
            raise ValueError(f"video url is not a supported absolute URL: {url}")

    def _path_segment(self, value: str) -> str:
        return quote(value, safe="")
