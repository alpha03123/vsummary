from __future__ import annotations

import asyncio
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import httpx


SERIES_EXPORT_KINDS = {"summary", "transcript", "mixed", "knowledge-cards", "notes"}
PROCESS_POLL_INTERVAL_SECONDS = 1.0
PROCESS_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
EXPORT_INLINE_LIMIT_CHARS = 3000
EXPORT_PREVIEW_CHARS = 2000
EXPORT_RESOURCE_SCHEME = "vsummary://exports"


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
        export_root: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.export_root = export_root or _default_export_root()

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
        force_file: bool = False,
        output_path: str | None = None,
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
        markdown_items: list[tuple[dict[str, Any], str]] = []
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
            markdown_items.append((items[-1], markdown))
        exported_markdown = [markdown for _, markdown in markdown_items]
        markdown_chars = sum(len(markdown) for markdown in exported_markdown)
        should_write_file = force_file or output_path is not None or markdown_chars > EXPORT_INLINE_LIMIT_CHARS
        if should_write_file:
            export = self._write_export_resource(
                series_id=series_id,
                kind=kind,
                markdown_items=markdown_items,
                output_path=output_path,
            )
            for item, markdown in markdown_items:
                item.pop("markdown", None)
                item["markdown_chars"] = len(markdown)
            result = {
                "series_id": series_id,
                "kind": kind,
                "delivery": export["delivery"],
                "exported_count": sum(1 for item in items if item["status"] == "exported"),
                "failed_count": sum(1 for item in items if item["status"] != "exported"),
                "markdown_chars": markdown_chars,
                "inline_limit_chars": EXPORT_INLINE_LIMIT_CHARS,
                "preview_chars": EXPORT_PREVIEW_CHARS,
                "preview": _truncate_text(export["markdown"], EXPORT_PREVIEW_CHARS),
                "truncated": len(export["markdown"]) > EXPORT_PREVIEW_CHARS,
                "resource_uri": export["resource_uri"],
                "resource_date": export["resource_date"],
                "filename": export["filename"],
                "relative_path": export["relative_path"],
                "output_path": export["output_path"],
                "items": items,
            }
            if export["resource_uri"]:
                result["resource_link"] = {
                    "type": "resource_link",
                    "uri": export["resource_uri"],
                    "name": export["filename"],
                    "description": f"VSummary {kind} export for series {series_id}",
                    "mimeType": "text/markdown",
                    "size": export["size"],
                }
            return result
        return {
            "series_id": series_id,
            "kind": kind,
            "delivery": "inline",
            "markdown_chars": markdown_chars,
            "inline_limit_chars": EXPORT_INLINE_LIMIT_CHARS,
            "exported_count": sum(1 for item in items if item["status"] == "exported"),
            "failed_count": sum(1 for item in items if item["status"] != "exported"),
            "items": items,
        }

    def read_export_resource(self, date: str, filename: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError(f"invalid export resource date: {date}")
        if not filename or Path(filename).name != filename:
            raise ValueError(f"invalid export resource filename: {filename}")
        path = (self.export_root / date / filename).resolve()
        root = self.export_root.resolve()
        if not path.is_file() or root not in path.parents:
            raise FileNotFoundError(f"export resource not found: {date}/{filename}")
        return path.read_text(encoding="utf-8")

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

    def _write_export_resource(
        self,
        *,
        series_id: str,
        kind: str,
        markdown_items: list[tuple[dict[str, Any], str]],
        output_path: str | None = None,
    ) -> dict[str, Any]:
        markdown = _combined_export_markdown(series_id=series_id, kind=kind, markdown_items=markdown_items)
        if output_path is not None:
            resolved_output_path = _resolve_requested_output_path(output_path)
            resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_output_path.write_text(markdown, encoding="utf-8", newline="\n")
            return {
                "delivery": "file",
                "markdown": markdown,
                "resource_uri": "",
                "resource_date": "",
                "filename": resolved_output_path.name,
                "relative_path": _display_path(resolved_output_path),
                "output_path": str(resolved_output_path),
                "size": resolved_output_path.stat().st_size,
            }

        now = datetime.now()
        resource_date = now.strftime("%Y-%m-%d")
        filename = _safe_export_filename(f"{now:%H%M%S-%f}-{series_id}-{kind}.md")
        export_dir = self.export_root / resource_date
        export_dir.mkdir(parents=True, exist_ok=True)
        resolved_output_path = export_dir / filename
        resolved_output_path.write_text(markdown, encoding="utf-8", newline="\n")
        relative_path = _display_path(resolved_output_path)
        resource_uri = f"{EXPORT_RESOURCE_SCHEME}/{resource_date}/{filename}"
        return {
            "delivery": "resource",
            "markdown": markdown,
            "resource_uri": resource_uri,
            "resource_date": resource_date,
            "filename": filename,
            "relative_path": relative_path,
            "output_path": str(resolved_output_path),
            "size": resolved_output_path.stat().st_size,
        }


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


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_export_root() -> Path:
    return _project_root() / "temp" / "mcp-exports"


def _safe_export_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not safe:
        raise ValueError("export filename cannot be empty")
    return safe


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(_project_root()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_requested_output_path(output_path: str) -> Path:
    path = Path(output_path).expanduser()
    if path.exists():
        if path.is_dir():
            raise IsADirectoryError(f"export output_path points to a directory: {output_path}")
        raise FileExistsError(f"export output_path already exists: {output_path}")
    return path.resolve()


def _combined_export_markdown(
    *,
    series_id: str,
    kind: str,
    markdown_items: list[tuple[dict[str, Any], str]],
) -> str:
    sections = [f"# VSummary export: {series_id}", "", f"- Kind: {kind}", ""]
    for item, markdown in markdown_items:
        sections.extend(
            [
                "---",
                "",
                f"<!-- video_id: {item.get('video_id', '')} -->",
                "",
                markdown.rstrip(),
                "",
            ]
        )
    return "\n".join(sections).rstrip() + "\n"


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    suffix = "\n\n...[truncated]"
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)].rstrip() + suffix


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
