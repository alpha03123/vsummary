from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Protocol

import httpx

from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.models import BilibiliUrlInfoDTO


class ProgressReporter(Protocol):
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None: ...
    def completed(self, detail: str | None = None) -> None: ...
    def failed(self, message: str) -> None: ...
    def cancelled(self, detail: str | None = None) -> None: ...
    def raise_if_cancelled(self) -> None: ...


class ProgressTracker(Protocol):
    def create_reporter(self, task_id: str) -> ProgressReporter: ...


class YtDlpBilibiliResolver:
    def __init__(
        self,
        extractor: Callable[[str], dict[str, object]] | None = None,
        view_extractor: Callable[[str], dict[str, object]] | None = None,
    ) -> None:
        self._extractor = extractor or _extract_info
        self._view_extractor = view_extractor or _extract_view_info

    async def resolve_series(self, url_info: BilibiliUrlInfoDTO) -> LinkedSeries:
        payload = await asyncio.to_thread(self._extractor, url_info.url)
        entries = [entry for entry in payload.get("entries", []) if isinstance(entry, dict)]
        should_fetch_view = not entries or _series_needs_view_titles(payload, entries)
        view_bvid, view_payload = (
            await _resolve_view_payload(payload, url_info.url, self._view_extractor)
            if should_fetch_view
            else ("", {})
        )
        if not entries:
            entries = _entries_from_view_payload(view_bvid=view_bvid, view_payload=view_payload)
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
        title_overrides = _extract_title_overrides(view_payload, root_bvid=view_bvid)
        videos = [
            _linked_video_from_payload(
                _merge_entry_title(entry, title_overrides=title_overrides),
                fallback_url=url_info.url,
            )
            for entry in entries
        ]
        series_key = _safe_series_key(str(payload.get("id") or videos[0].video_id))
        series_title = _as_text(payload.get("title"))
        if _is_bvid_title(series_title):
            series_title = _extract_series_title(view_payload)
        return LinkedSeries(
            series_id=f"bilibili-{series_key}",
            title=series_title or videos[0].title,
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
        progress_tracker: ProgressTracker,
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


def _extract_view_info(bvid: str) -> dict[str, object]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
    }
    response = httpx.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise RuntimeError(f"Bilibili view API 返回异常：{payload.get('message') if isinstance(payload, dict) else payload}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Bilibili view API 未返回有效 data。")
    return data


async def _resolve_view_payload(
    payload: dict[str, object],
    fallback_url: str,
    view_extractor: Callable[[str], dict[str, object]],
) -> tuple[str, dict[str, object]]:
    try:
        bvid = _extract_bvid(payload)
    except ValueError:
        bvid = _extract_bvid_from_entries(payload) or _extract_bvid_from_text(fallback_url)
        if not bvid:
            return "", {}
    return bvid, await asyncio.to_thread(view_extractor, bvid)


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


def _series_needs_view_titles(payload: dict[str, object], entries: list[dict[str, object]]) -> bool:
    if _is_bvid_title(_as_text(payload.get("title"))):
        return True
    return any(not _as_text(entry.get("title")) or _is_bvid_title(_as_text(entry.get("title"))) for entry in entries)


def _entries_from_view_payload(*, view_bvid: str, view_payload: dict[str, object]) -> list[dict[str, object]]:
    season = view_payload.get("ugc_season")
    if isinstance(season, dict):
        entries = _entries_from_ugc_season(season)
        if entries:
            return entries

    pages = view_payload.get("pages")
    if not isinstance(pages, list) or not view_bvid:
        return []
    entries: list[dict[str, object]] = []
    for item in pages:
        if not isinstance(item, dict):
            continue
        page = _as_positive_int(item.get("page"), 1)
        entries.append(
            {
                "id": view_bvid,
                "title": _as_text(item.get("part")) or _as_text(view_payload.get("title")) or view_bvid,
                "page_number": page,
                "duration": _as_int(item.get("duration")),
                "thumbnail": _as_text(view_payload.get("pic")) or _as_text(view_payload.get("thumbnail")),
                "webpage_url": _page_url(view_bvid, page),
            }
        )
    return entries


def _entries_from_ugc_season(season: dict[str, object]) -> list[dict[str, object]]:
    sections = season.get("sections")
    if not isinstance(sections, list):
        return []
    entries: list[dict[str, object]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        episodes = section.get("episodes")
        if not isinstance(episodes, list):
            continue
        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            bvid = _as_text(episode.get("bvid"))
            if not bvid:
                continue
            entries.append(
                {
                    "id": bvid,
                    "title": _as_text(episode.get("title")) or bvid,
                    "duration": _as_int(episode.get("duration")),
                    "thumbnail": _as_text(episode.get("cover")),
                    "webpage_url": _page_url(bvid, 1),
                }
            )
    return entries


def _merge_entry_title(
    entry: dict[str, object],
    *,
    title_overrides: dict[tuple[str, int], str],
) -> dict[str, object]:
    bvid = _extract_bvid(entry)
    page = _extract_page(entry)
    current_title = _as_text(entry.get("title"))
    override = title_overrides.get((bvid, page)) or title_overrides.get((bvid, 1))
    if not override:
        return entry
    return {**entry, "title": override}


def _extract_title_overrides(view_payload: dict[str, object], *, root_bvid: str) -> dict[tuple[str, int], str]:
    overrides: dict[tuple[str, int], str] = {}
    root_bvid = _as_text(view_payload.get("bvid")) or root_bvid
    pages = view_payload.get("pages")
    if isinstance(pages, list):
        for item in pages:
            if not isinstance(item, dict):
                continue
            page = _as_positive_int(item.get("page"), 1)
            title = _as_text(item.get("part"))
            if root_bvid and title:
                overrides[(root_bvid, page)] = title

    season = view_payload.get("ugc_season")
    if isinstance(season, dict):
        sections = season.get("sections")
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                episodes = section.get("episodes")
                if not isinstance(episodes, list):
                    continue
                for episode in episodes:
                    if not isinstance(episode, dict):
                        continue
                    bvid = _as_text(episode.get("bvid"))
                    title = _as_text(episode.get("title"))
                    if bvid and title:
                        overrides.setdefault((bvid, 1), title)
    return overrides


def _page_url(bvid: str, page: int) -> str:
    url = f"https://www.bilibili.com/video/{bvid}"
    return f"{url}?p={page}" if page > 1 else url


def _extract_series_title(view_payload: dict[str, object]) -> str:
    season = view_payload.get("ugc_season")
    if isinstance(season, dict):
        title = _as_text(season.get("title"))
        if title:
            return title
    return _as_text(view_payload.get("title"))


def _extract_bvid(payload: dict[str, object]) -> str:
    candidates = [payload.get("id"), payload.get("display_id"), payload.get("webpage_url"), payload.get("url")]
    for value in candidates:
        bvid = _extract_bvid_from_text(str(value or ""))
        if bvid:
            return bvid
    raise ValueError("yt-dlp 元数据中缺少 Bilibili BV 号。")


def _extract_bvid_from_entries(payload: dict[str, object]) -> str:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return ""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            return _extract_bvid(entry)
        except ValueError:
            continue
    return ""


def _extract_bvid_from_text(value: str) -> str:
    match = re.search(r"(BV[a-zA-Z0-9]{10})", value)
    return match.group(1) if match else ""


def _extract_page(payload: dict[str, object]) -> int:
    for key in ("page_number", "playlist_index"):
        value = payload.get(key)
        if isinstance(value, int) and value > 0:
            return value
    for key in ("webpage_url", "url"):
        page = _extract_page_from_text(_as_text(payload.get(key)))
        if page > 0:
            return page
    return 1


def _extract_page_from_text(value: str) -> int:
    match = re.search(r"(?:[?&]p=)(\d+)", value)
    if match is None:
        return 0
    return int(match.group(1))


def _as_positive_int(value: object, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return fallback


def _is_bvid_title(value: str) -> bool:
    return bool(re.fullmatch(r"BV[a-zA-Z0-9]{10}(?:_p\d+)?", value.strip()))


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
