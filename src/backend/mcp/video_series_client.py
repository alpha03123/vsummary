from __future__ import annotations

import asyncio
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import httpx


SERIES_EXPORT_KINDS = {"summary", "transcript", "mixed", "knowledge-cards", "notes"}
PROCESS_POLL_INTERVAL_SECONDS = 1.0
PROCESS_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class BackendApiError(RuntimeError):
    """Error returned by the local VSummary backend."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Backend API error {status_code}: {detail}")


class VideoSeriesBackendClient:
    """HTTP adapter used by MCP tools to call the local FastAPI backend."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def get_project_status(self, include_series: bool = True) -> dict[str, Any]:
        health = await self._request_json("GET", "/api/health")
        result: dict[str, Any] = {
            "backend": {**health, "base_url": self.base_url},
            "bilibili": {"cookie_configured": "unknown"},
            "series": [],
        }
        if not include_series:
            return result

        library = await self._request_json("GET", "/api/videos")
        result["series"] = [_series_summary(series) for series in library.get("series", [])]
        return result

    async def create_series(self, title: str) -> dict[str, Any]:
        if not title.strip():
            raise ValueError("title must not be blank")
        series = await self._request_json(
            "POST",
            "/api/agent/series",
            json={"title": title},
        )
        return {
            "series_id": series["id"],
            "title": series["title"],
            "is_agent_managed": bool(series.get("is_agent_managed")),
            "videos": series.get("videos", []),
        }

    async def add_series_videos(self, series_id: str, videos: list[dict[str, Any]]) -> dict[str, Any]:
        self._require_series_id(series_id)
        if not videos:
            raise ValueError("videos must not be empty")

        items = []
        for video in videos:
            url = video.get("url", "")
            self._validate_video_url(url)
            try:
                resolved = await self._request_json(
                    "POST",
                    "/api/linked/bilibili/resolve/video",
                    json={"url": url, "target_series_id": series_id},
                )
            except BackendApiError as error:
                items.append({"url": url, "status": "failed", "error": error.detail})
                continue
            items.append(
                {
                    "url": url,
                    "status": "added",
                    "video_id": resolved.get("id", ""),
                    "title": resolved.get("title", ""),
                }
            )
        return {
            "series_id": series_id,
            "added_count": sum(1 for item in items if item["status"] == "added"),
            "failed_count": sum(1 for item in items if item["status"] != "added"),
            "items": items,
        }

    async def import_local_series(self, title: str, file_paths: list[str]) -> dict[str, Any]:
        if not title.strip():
            raise ValueError("title must not be blank")
        media_paths = _resolve_local_media_paths(file_paths)
        with ExitStack() as stack:
            files = [("files", (path.name, stack.enter_context(path.open("rb")))) for path in media_paths]
            series = await self._request_json(
                "POST",
                "/api/import/local/series",
                data={"series_title": title},
                files=files,
            )
        return {
            "series_id": series["id"],
            "title": series["title"],
            "videos": series.get("videos", []),
        }

    async def add_local_series_videos(self, series_id: str, file_paths: list[str]) -> dict[str, Any]:
        self._require_series_id(series_id)
        media_paths = _resolve_local_media_paths(file_paths)
        with ExitStack() as stack:
            files = [("files", (path.name, stack.enter_context(path.open("rb")))) for path in media_paths]
            videos = await self._request_json(
                "POST",
                f"/api/import/local/series/{self._path_segment(series_id)}",
                files=files,
            )
        return {
            "series_id": series_id,
            "added_count": len(videos),
            "videos": videos,
        }

    async def process_series(
        self,
        series_id: str,
        video_ids: list[str] | None = None,
        run_id: str | None = None,
        transcript_enhancement_enabled: bool | None = None,
        wait: bool = False,
    ) -> dict[str, Any]:
        self._require_series_id(series_id)
        normalized_video_ids = _normalized_ids(video_ids or [])
        if wait:
            return await self._process_series_waiting(
                series_id=series_id,
                video_ids=normalized_video_ids,
                run_id=run_id,
                transcript_enhancement_enabled=transcript_enhancement_enabled,
            )
        return await self._request_json(
            "POST",
            f"/api/agent/series/{self._path_segment(series_id)}/process",
            json={
                "video_ids": normalized_video_ids,
                "run_id": run_id,
                "transcript_enhancement_enabled": transcript_enhancement_enabled,
            },
        )

    async def get_series_status(self, series_id: str, video_ids: list[str] | None = None) -> dict[str, Any]:
        self._require_series_id(series_id)
        series = await self._get_series(series_id)
        selected_ids = set(_normalized_ids(video_ids or []))
        videos = [
            video
            for video in series.get("videos", [])
            if not selected_ids or str(video.get("id", "")) in selected_ids
        ]
        series_generation = await self._request_json(
            "GET",
            f"/api/series/{self._path_segment(series_id)}/generate/status",
        )
        video_items = []
        for video in videos:
            video_id = str(video.get("id", ""))
            generation = await self._request_json(
                "GET",
                f"/api/videos/{self._path_segment(series_id)}/{self._path_segment(video_id)}/generate/status",
            )
            video_items.append(_video_status(video, generation))
        return {
            "series_id": series["id"],
            "title": series["title"],
            "is_agent_managed": bool(series.get("is_agent_managed")),
            "overall_status": _overall_status(series_generation, video_items),
            "completed_count": sum(1 for item in video_items if item["processed"]),
            "total_count": len(video_items),
            "series_generation": _snapshot_payload(series_generation),
            "videos": video_items,
        }

    async def export_series(
        self,
        series_id: str,
        kind: str = "mixed",
        video_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_series_id(series_id)
        if kind not in SERIES_EXPORT_KINDS:
            raise ValueError(f"unsupported markdown export kind: {kind}")
        series = await self._get_series(series_id)
        selected_ids = set(_normalized_ids(video_ids or []))
        videos = [
            video
            for video in series.get("videos", [])
            if not selected_ids or str(video.get("id", "")) in selected_ids
        ]
        items = []
        for video in videos:
            video_id = str(video.get("id", ""))
            try:
                markdown = await self._request_text(
                    "GET",
                    f"/api/videos/{self._path_segment(series_id)}/{self._path_segment(video_id)}/exports/{kind}.md",
                )
            except BackendApiError as error:
                items.append(
                    {
                        "video_id": video_id,
                        "title": video.get("title", ""),
                        "status": "missing" if error.status_code == 404 else "failed",
                        "error": error.detail,
                    }
                )
                continue
            items.append(
                {
                    "video_id": video_id,
                    "title": video.get("title", ""),
                    "status": "exported",
                    "markdown": markdown,
                }
            )
        return {
            "series_id": series_id,
            "kind": kind,
            "exported_count": sum(1 for item in items if item["status"] == "exported"),
            "failed_count": sum(1 for item in items if item["status"] != "exported"),
            "items": items,
        }

    async def delete_series(self, series_id: str) -> dict[str, Any]:
        self._require_series_id(series_id)
        return await self._request_json(
            "DELETE",
            f"/api/series/{self._path_segment(series_id)}",
        )

    async def _process_series_waiting(
        self,
        *,
        series_id: str,
        video_ids: list[str],
        run_id: str | None,
        transcript_enhancement_enabled: bool | None,
    ) -> dict[str, Any]:
        scheduled = await self._request_json(
            "POST",
            f"/api/agent/series/{self._path_segment(series_id)}/process",
            json={
                "video_ids": video_ids,
                "run_id": run_id,
                "transcript_enhancement_enabled": transcript_enhancement_enabled,
            },
        )
        while True:
            status = await self.get_series_status(series_id, video_ids=video_ids)
            if status["overall_status"] in PROCESS_TERMINAL_STATUSES:
                return {
                    "status": status["overall_status"],
                    "series_id": series_id,
                    "scope": scheduled.get("scope", "series"),
                    "video_ids": video_ids,
                    "scheduled": scheduled,
                    "result": status,
                }
            await asyncio.sleep(PROCESS_POLL_INTERVAL_SECONDS)

    async def _get_series(self, series_id: str) -> dict[str, Any]:
        library = await self._request_json("GET", "/api/videos")
        for series in library.get("series", []):
            if series.get("id") == series_id:
                return series
        raise BackendApiError(404, f"series not found '{series_id}'")

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if not response.content:
            return {}
        return response.json()

    async def _request_text(self, method: str, path: str, **kwargs: Any) -> str:
        response = await self._request(method, path, **kwargs)
        return response.text

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise BackendApiError(response.status_code, _error_detail(response))
        return response

    def _require_series_id(self, series_id: str) -> None:
        if not series_id.strip():
            raise ValueError("series_id must not be blank")

    def _validate_video_url(self, url: object) -> None:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("video url must not be blank")
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path:
            raise ValueError(f"video url is not a supported absolute URL: {url}")

    def _path_segment(self, value: str) -> str:
        return quote(value, safe="")


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)


def _series_summary(series: dict[str, Any]) -> dict[str, Any]:
    videos = series.get("videos", [])
    return {
        "id": series.get("id", ""),
        "title": series.get("title", ""),
        "video_count": len(videos),
        "processed_count": sum(1 for video in videos if video.get("processed")),
        "linked_count": sum(1 for video in videos if video.get("is_linked")),
        "is_agent_managed": bool(series.get("is_agent_managed")),
    }


def _video_status(video: dict[str, Any], generation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": video.get("id", ""),
        "title": video.get("title", ""),
        "status": video.get("status", ""),
        "processed": bool(video.get("processed")),
        "is_linked": bool(video.get("is_linked")),
        "generation": _snapshot_payload(generation),
    }


def _snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = payload.get("snapshot", {})
    return {
        "task_id": payload.get("task_id", ""),
        "status": snapshot.get("status", "idle"),
        "progress": snapshot.get("progress"),
        "detail": snapshot.get("detail", ""),
        "error": snapshot.get("error", ""),
    }


def _overall_status(series_generation: dict[str, Any], videos: list[dict[str, Any]]) -> str:
    if videos and all(video["processed"] for video in videos):
        return "completed"
    video_statuses = {video["generation"]["status"] for video in videos}
    if video_statuses & {"running", "processing", "downloading", "transcribing", "summarizing"}:
        return "processing"
    if video_statuses & {"failed"}:
        return "failed"
    if video_statuses & {"cancelled"}:
        return "cancelled"
    series_status = _snapshot_payload(series_generation)["status"]
    if series_status == "completed" and videos:
        return "pending"
    if series_status not in {"idle", ""}:
        return series_status
    return "pending"


def _normalized_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def _resolve_local_media_paths(file_paths: list[str]) -> list[Path]:
    if not file_paths:
        raise ValueError("file_paths must not be empty")
    resolved = []
    for file_path in file_paths:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"local media file not found: {file_path}")
        resolved.append(path)
    return resolved
