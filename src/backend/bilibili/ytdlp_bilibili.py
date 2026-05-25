from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Protocol

from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.models import BilibiliUrlInfoDTO


class ProgressReporter(Protocol):
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None: ...
    def completed(self, detail: str | None = None) -> None: ...
    def failed(self, message: str) -> None: ...
    def cancelled(self, detail: str | None = None) -> None: ...
    def raise_if_cancelled(self) -> None: ...


class YtDlpBilibiliResolver:
    def __init__(self, extractor: Callable[[str], dict[str, object]] | None = None) -> None:
        self._extractor = extractor or _extract_info

    async def resolve_series(self, url_info: BilibiliUrlInfoDTO) -> LinkedSeries:
        payload = await asyncio.to_thread(self._extractor, url_info.url)
        entries = [entry for entry in payload.get("entries", []) if isinstance(entry, dict)]
        if not entries:
            single = _linked_video_from_payload(payload, fallback_url=url_info.url)
            entries = [
                {
                    "id": single.bvid,
                    "title": single.title,
                    "duration": single.duration_seconds,
                    "thumbnail": single.cover_url,
                    "webpage_url": single.source_url,
                }
            ]
        videos = [_linked_video_from_payload(entry, fallback_url=url_info.url) for entry in entries]
        series_key = _safe_series_key(str(payload.get("id") or videos[0].video_id))
        return LinkedSeries(
            series_id=f"bilibili-{series_key}",
            title=_as_text(payload.get("title")) or videos[0].title,
            cover_url=_as_text(payload.get("thumbnail")),
            source_url=_as_text(payload.get("webpage_url")) or url_info.url,
            videos=videos,
        )

    async def resolve_single_video(self, url_info: BilibiliUrlInfoDTO) -> LinkedVideo:
        payload = await asyncio.to_thread(self._extractor, url_info.url)
        return _linked_video_from_payload(payload, fallback_url=url_info.url)


class BilibiliDownloader:
    _PROGRESS_RE = re.compile(r"\[download\]\s+([\d.]+)%")

    def download(self, bvid: str, page: int, dest_dir: Path, reporter: ProgressReporter) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem = bvid if page == 1 else f"{bvid}_p{page}"
        url = f"https://www.bilibili.com/video/{bvid}"
        if page > 1:
            url = f"{url}?p={page}"
        output_template = str(dest_dir / f"{stem}.%(ext)s")
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--merge-output-format",
            "mp4",
            "--output",
            output_template,
            "--newline",
            "--no-part",
            url,
        ]
        reporter.update("download", 0.0, "开始下载")
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if process.stdout is None:
                raise RuntimeError("无法读取 yt-dlp 输出。")
            last_percent = -1.0
            for line in process.stdout:
                reporter.raise_if_cancelled()
                match = self._PROGRESS_RE.search(line.rstrip())
                if match is None:
                    continue
                percent = float(match.group(1))
                if percent == last_percent:
                    continue
                last_percent = percent
                reporter.update("download", percent, f"下载中 {percent:.1f}%")
            process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"yt-dlp 退出码 {process.returncode}")
        except Exception as exc:
            reporter.failed(str(exc))
            raise

        candidates = sorted(dest_dir.glob(f"{stem}.*"))
        if not candidates:
            message = f"yt-dlp 下载完成但未找到输出文件：{stem}.*"
            reporter.failed(message)
            raise RuntimeError(message)
        reporter.completed(f"下载完成：{candidates[0].name}")
        return candidates[0]

    async def download_async(self, bvid: str, page: int, dest_dir: Path, reporter: ProgressReporter) -> Path:
        return await asyncio.to_thread(self.download, bvid, page, dest_dir, reporter)


def build_video_download_task_id(series_id: str, video_id: str) -> str:
    return f"download/{series_id}/{video_id}"


class BackgroundBilibiliDownloadStarter:
    def __init__(
        self,
        *,
        root_dir: Path,
        downloader: BilibiliDownloader,
        progress_tracker: InMemoryProgressTracker,
    ) -> None:
        self._root_dir = root_dir
        self._downloader = downloader
        self._progress_tracker = progress_tracker

    def start(self, *, series_id: str, video_id: str, bvid: str, page: int) -> str:
        task_id = build_video_download_task_id(series_id, video_id)
        reporter = self._progress_tracker.create_reporter(task_id)
        dest_dir = self._root_dir / "videos" / series_id

        async def _run() -> None:
            try:
                await self._downloader.download_async(bvid, page, dest_dir, reporter)
            except Exception:
                pass

        asyncio.create_task(_run())
        return task_id


def _extract_info(url: str) -> dict[str, object]:
    from yt_dlp import YoutubeDL

    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    with YoutubeDL(options) as ydl:
        payload = ydl.extract_info(url, download=False)
    if not isinstance(payload, dict):
        raise RuntimeError("yt-dlp 未返回有效元数据。")
    return payload


def _linked_video_from_payload(payload: dict[str, object], *, fallback_url: str) -> LinkedVideo:
    bvid = _extract_bvid(payload)
    page = _extract_page(payload)
    source_url = _as_text(payload.get("webpage_url")) or _as_text(payload.get("url")) or fallback_url
    if source_url.startswith("//"):
        source_url = f"https:{source_url}"
    if not source_url.startswith("http"):
        source_url = f"https://www.bilibili.com/video/{bvid}"
    if page > 1 and "?" not in source_url:
        source_url = f"{source_url}?p={page}"
    return LinkedVideo(
        bvid=bvid,
        page=page,
        title=_as_text(payload.get("title")) or bvid,
        cover_url=_as_text(payload.get("thumbnail")),
        duration_seconds=_as_int(payload.get("duration")),
        source_url=source_url,
    )


def _extract_bvid(payload: dict[str, object]) -> str:
    candidates = [payload.get("id"), payload.get("display_id"), payload.get("webpage_url"), payload.get("url")]
    for value in candidates:
        match = re.search(r"(BV[a-zA-Z0-9]{10})", str(value or ""))
        if match:
            return match.group(1)
    raise ValueError("yt-dlp 元数据中缺少 Bilibili BV 号。")


def _extract_page(payload: dict[str, object]) -> int:
    for key in ("page_number", "playlist_index"):
        value = payload.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return 1


def _safe_series_key(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return normalized or "linked-series"


def _as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0
