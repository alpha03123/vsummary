from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import tempfile
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


class DownloadCancelled(RuntimeError):
    pass


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
        # 原始命令（已注释）：v1 没设 User-Agent / Referer，B 站返回 412。
        # cmd = [
        #     sys.executable, "-m", "yt_dlp",
        #     "--no-playlist", "--merge-output-format", "mp4",
        #     "--output", output_template, "--newline", "--no-part",
        #     url,
        # ]
        # v2（已注释）：加了 User-Agent / Referer / Cookie，但没关代理。
        # bilibili_headers = _load_bilibili_headers()
        # cmd = [
        #     sys.executable, "-m", "yt_dlp",
        #     "--no-playlist", "--merge-output-format", "mp4",
        #     "--output", output_template, "--newline", "--no-part",
        #     *_build_yt_dlp_add_header_flags(bilibili_headers),
        #     url,
        # ]
        # v3（已注释）：加了 --proxy "" 和 --add-header Cookie，但 Cookie 经
        # --add-header 注入会被 yt-dlp 的 cookiejar 覆盖，playinfo 端点照样 412。
        # bilibili_headers = _load_bilibili_headers()
        # cmd = [
        #     sys.executable, "-m", "yt_dlp",
        #     "--no-playlist", "--merge-output-format", "mp4",
        #     "--output", output_template, "--newline", "--no-part",
        #     "--proxy", "",
        #     *_build_yt_dlp_add_header_flags(bilibili_headers),
        #     url,
        # ]
        # v4：Cookie 走 --cookies Netscape 文件，UA/Referer 走 --add-header。
        bilibili_headers = _load_bilibili_headers()
        # Cookie 单独提走，避免和 --cookies 重复注入。
        cookie_value = bilibili_headers.pop("Cookie", None)
        cookies_path = _write_bilibili_cookies_file(cookie_value or "")
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
            "--proxy", "",  # 显式不走代理：B 站是境内站点，代理握手会失败。
        ]
        if cookies_path is not None:
            cmd.extend(["--cookies", str(cookies_path)])
        cmd.extend([*_build_yt_dlp_add_header_flags(bilibili_headers), url])
        # 子进程清掉代理相关环境变量（防 ffmpeg 等子进程走系统代理）。
        proc_env = {
            k: v
            for k, v in os.environ.items()
            if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}
        }
        reporter.update("download", 0.0, "开始下载")
        process = None
        # 收集 yt-dlp 最近 50 行输出，失败时拼进错误信息便于排错。
        output_tail: list[str] = []
        # v1 Popen（已注释）：没传 env=，子进程继承系统代理。
        # try:
        #     process = subprocess.Popen(
        #         cmd,
        #         stdout=subprocess.PIPE,
        #         stderr=subprocess.STDOUT,
        #         text=True,
        #         encoding="utf-8",
        #         errors="replace",
        #     )
        # v2 Popen：传 env=，子进程不携带代理；外加 finally 清理 cookies 临时文件。
        try:
            process = subprocess.Popen(
                cmd,
                env=proc_env,
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
                stripped = line.rstrip()
                output_tail.append(stripped)
                if len(output_tail) > 50:
                    output_tail.pop(0)
                if _download_cancel_requested(reporter):
                    process.terminate()
                    raise DownloadCancelled("下载已取消")
                match = self._PROGRESS_RE.search(stripped)
                if match is None:
                    continue
                percent = float(match.group(1))
                if percent == last_percent:
                    continue
                last_percent = percent
                reporter.update("download", percent, f"下载中 {percent:.1f}%")
            process.wait()
            # v1 错误（已注释）：只报退出码，看不到 yt-dlp 实际报错。
            # if process.returncode != 0:
            #     raise RuntimeError(f"yt-dlp 退出码 {process.returncode}")
            # v2 错误：把 yt-dlp 最后输出拼进来。
            if process.returncode != 0:
                tail_text = "\n".join(output_tail).strip() or "(无输出)"
                raise RuntimeError(
                    f"yt-dlp 退出码 {process.returncode}。\nyt-dlp 最后输出：\n{tail_text}"
                )
        except DownloadCancelled as exc:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            reporter.cancelled(str(exc))
            raise
        except Exception as exc:
            reporter.failed(str(exc))
            raise
        finally:
            # 不管成功 / 失败 / 取消，都清理临时 cookies 文件。
            if cookies_path is not None:
                try:
                    cookies_path.unlink(missing_ok=True)
                except Exception:
                    pass

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


def _download_cancel_requested(reporter: ProgressReporter) -> bool:
    try:
        reporter.raise_if_cancelled()
    except RuntimeError:
        return True
    return False


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

    def start_video(self, *, series_id: str, video) -> str:
        return self.start(series_id=series_id, video_id=video.video_id, bvid=video.bvid, page=video.page)


class BilibiliLinkedVideoDownloadStarter:
    def __init__(self, starter: BackgroundBilibiliDownloadStarter) -> None:
        self._starter = starter

    def start(self, *, series_id: str, video) -> str:
        if video.provider != "bilibili":
            raise RuntimeError(f"unsupported linked video provider '{video.provider}'")
        return self._starter.start_video(series_id=series_id, video=video)


class CompositeLinkedVideoDownloadStarter:
    def __init__(self, starters: dict[str, object]) -> None:
        self._starters = starters

    def start(self, *, series_id: str, video) -> str:
        starter = self._starters.get(video.provider)
        if starter is None:
            raise RuntimeError(f"unsupported linked video provider '{video.provider}'")
        return starter.start(series_id=series_id, video=video)


# B 站反爬要求：标准浏览器 UA + Referer，否则会返回 412。
# 可选地从 BILIBILI_COOKIE（完整字符串，优先级最高）或 BILIBILI_SESSDATA（单 cookie）
# 环境变量读取登录态 Cookie，进一步过 playinfo WAF。
_BILIBILI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_BILIBILI_REFERER = "https://www.bilibili.com/"
_BILIBILI_COOKIE_ENV = "BILIBILI_COOKIE"
_BILIBILI_SESSDATA_ENV = "BILIBILI_SESSDATA"


def _load_bilibili_headers() -> dict[str, str]:
    """构造 B 站请求头。

    优先读 BILIBILI_COOKIE（浏览器 DevTools 复制的完整 Cookie 字符串，
    包含 SESSDATA / buvid3 / buvid4 / b_nut / bili_jct / _uuid 等，
    playinfo 接口必需）；未设置时回退到 BILIBILI_SESSDATA（单 cookie，
    兼容旧配置，覆盖面不够）。两者都没设就不带 Cookie。
    """
    # 原始实现（已注释）：只支持单 SESSDATA，过不了 playinfo WAF。
    # headers: dict[str, str] = {
    #     "User-Agent": _BILIBILI_USER_AGENT,
    #     "Referer": _BILIBILI_REFERER,
    # }
    # sessdata = os.environ.get(_BILIBILI_SESSDATA_ENV, "").strip()
    # if sessdata:
    #     headers["Cookie"] = f"SESSDATA={sessdata}"
    # return headers
    headers: dict[str, str] = {
        "User-Agent": _BILIBILI_USER_AGENT,
        "Referer": _BILIBILI_REFERER,
    }
    full_cookie = os.environ.get(_BILIBILI_COOKIE_ENV, "").strip()
    if full_cookie:
        headers["Cookie"] = full_cookie
        return headers
    sessdata = os.environ.get(_BILIBILI_SESSDATA_ENV, "").strip()
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"
    return headers


def _build_yt_dlp_add_header_flags(headers: dict[str, str]) -> list[str]:
    """把 headers 字典展开成 yt-dlp 的 --add-header 参数列表。"""
    flags: list[str] = []
    for key, value in headers.items():
        flags.extend(["--add-header", f"{key}:{value}"])
    return flags


def _write_bilibili_cookies_file(cookie_string: str) -> Path | None:
    """把 B 站 Cookie 字符串写成 Netscape 格式临时文件，返回路径。

    yt-dlp 的 B 站提取器对 playinfo 端点走 cookiejar 路径处理 Cookie，
    --add-header "Cookie:..." 注入的 header 在这一步可能被覆盖。
    用 --cookies 加载 Netscape 文件走 cookiejar 才能稳定生效。
    """
    cookie_string = cookie_string.strip()
    if not cookie_string:
        return None
    cookies: list[tuple[str, str]] = []
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        cookies.append((name.strip(), value.strip()))
    if not cookies:
        return None
    # Netscape 格式：domain TAB include_subdomains TAB path TAB secure TAB expires TAB name TAB value
    lines = ["# Netscape HTTP Cookie File"]
    for name, value in cookies:
        lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    content = "\n".join(lines) + "\n"
    fd, path_str = tempfile.mkstemp(suffix=".txt", prefix="bilibili_cookies_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        os.close(fd)
        raise
    return Path(path_str)


def _extract_info(url: str) -> dict[str, object]:
    from yt_dlp import YoutubeDL

    # 原始 options（已注释）：缺少 http_headers，B 站会返回 412。
    # options = {
    #     "quiet": True,
    #     "no_warnings": True,
    #     "extract_flat": "in_playlist",
    #     "skip_download": True,
    # }
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "http_headers": _load_bilibili_headers(),
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
    # 原始 httpx.get（已注释）：默认会读系统 HTTPS_PROXY，代理与 api.bilibili.com 的
    # TLS 握手失败（SSL: UNEXPECTED_EOF_WHILE_READING）。
    # response = httpx.get(
    #     "https://api.bilibili.com/x/web-interface/view",
    #     params={"bvid": bvid},
    #     headers=headers,
    #     timeout=20,
    # )
    response = httpx.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        headers=headers,
        timeout=20,
        proxy=None,  # B 站是境内站点，显式不走代理，避免代理握手失败。
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
