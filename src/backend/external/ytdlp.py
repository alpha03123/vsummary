"""YouTube、抖音等平台共用的 yt-dlp 链接适配器。"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Protocol

from backend.shared.filesystem import atomic_write_text
from backend.shared.ytdlp import parse_cookie_pairs, write_cookies_file
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo

_DEFAULT_USER_AGENT = "Mozilla/5.0"
_PROGRESS_RE = re.compile(r"\[download\]\s+([\d.]+)%")
LOGGER = logging.getLogger(__name__)


class ExternalCookieInitError(RuntimeError):
    """平台登录页无法取得可用 Cookie。"""


class ExternalVideoResolutionError(RuntimeError):
    """外部视频平台拒绝或无法解析链接。"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class DownloadCancelled(RuntimeError):
    """下载被取消。"""


class ProgressReporter(Protocol):
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None: ...
    def completed(self, detail: str | None = None) -> None: ...
    def failed(self, message: str) -> None: ...
    def cancelled(self, detail: str | None = None) -> None: ...
    def raise_if_cancelled(self) -> None: ...


class ProgressTracker(Protocol):
    def create_reporter(self, task_id: str) -> ProgressReporter: ...


@dataclass(frozen=True)
class YtDlpPlatform:
    provider: str
    display_name: str
    cookie_domain: str
    login_url: str
    cookie_env: str
    browser_port: int
    login_cookie_names: tuple[str, ...]
    format_selector: str = "bv*+ba/best"


class DrissionCookieInitializer:
    """通过独立浏览器 profile 登录平台并保存该平台 Cookie。"""

    def __init__(
        self,
        *,
        root_dir: Path,
        platform: YtDlpPlatform,
        page_factory: Callable[[str, int], object] | None = None,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._root_dir = root_dir
        self._platform = platform
        self._page_factory = page_factory or _create_drission_page
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds

    def init(self) -> bool:
        page = self._page_factory(
            str(self._root_dir / "data" / self._platform.provider / "browser"),
            self._platform.browser_port,
        )
        try:
            _page_get(page, self._platform.login_url)
            deadline = time.monotonic() + self._timeout_seconds
            while time.monotonic() <= deadline:
                cookie_header = _format_cookie_header(_page_cookies(page), self._platform.cookie_domain)
                if _has_login_cookie(cookie_header, self._platform.login_cookie_names):
                    _write_dotenv_value(self._root_dir / ".env", self._platform.cookie_env, cookie_header)
                    os.environ[self._platform.cookie_env] = cookie_header
                    return True
                time.sleep(self._poll_interval_seconds)
            raise ExternalCookieInitError(f"{self._platform.display_name} 登录超时，未获取到 Cookie。")
        except ExternalCookieInitError:
            raise
        except Exception as error:
            raise ExternalCookieInitError("浏览器已被关闭") from error
        finally:
            _close_page(page)


class YtDlpPlatformResolver:
    """将 yt-dlp 元数据映射为平台无关的链接系列和视频。"""

    def __init__(
        self,
        platform: YtDlpPlatform,
        extractor: Callable[[str], dict[str, object]] | None = None,
    ) -> None:
        self._platform = platform
        self._extractor = extractor or self._extract_info

    async def resolve_series(self, url_info) -> LinkedSeries:
        url = url_info.url
        payload = await self._extract(url)
        entries = [entry for entry in payload.get("entries", []) if isinstance(entry, dict)]
        videos = [self._to_video(entry, fallback_url=url) for entry in entries]
        if not videos:
            videos = [self._to_video(payload, fallback_url=url)]
        series_key = _safe_key(_text(payload.get("id")) or videos[0].source_id)
        return LinkedSeries(
            series_id=f"{self._platform.provider}-{series_key}",
            title=_text(payload.get("title")) or videos[0].title,
            cover_url=_text(payload.get("thumbnail")),
            source_url=_source_url(payload, url),
            videos=videos,
        )

    async def resolve_single_video(self, url_info) -> LinkedVideo:
        payload = await self._extract(url_info.url)
        return self._to_video(payload, fallback_url=url_info.url)

    async def _extract(self, url: str) -> dict[str, object]:
        try:
            return await asyncio.to_thread(self._extractor, url)
        except ExternalVideoResolutionError:
            raise
        except Exception as error:
            raise _external_platform_error(error) from error

    def _extract_info(self, url: str) -> dict[str, object]:
        from yt_dlp import YoutubeDL

        cookie_file = write_cookies_file(os.environ.get(self._platform.cookie_env, ""), self._platform.cookie_domain)
        options: dict[str, object] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "http_headers": {"User-Agent": _DEFAULT_USER_AGENT},
        }
        if cookie_file is not None:
            options["cookiefile"] = str(cookie_file)
        try:
            with YoutubeDL(options) as ydl:
                payload = ydl.extract_info(url, download=False)
        finally:
            if cookie_file is not None:
                cookie_file.unlink(missing_ok=True)
        if not isinstance(payload, dict):
            raise RuntimeError("yt-dlp 未返回有效元数据。")
        return payload

    def _to_video(self, payload: dict[str, object], *, fallback_url: str) -> LinkedVideo:
        source_id = _safe_key(_text(payload.get("id")) or _text(payload.get("display_id")))
        if not source_id:
            raise RuntimeError(f"{self._platform.display_name} 视频缺少稳定标识。")
        source_url = _source_url(payload, fallback_url)
        if source_url == fallback_url and self._platform.provider == "youtube":
            source_url = f"https://www.youtube.com/watch?v={source_id}"
        return LinkedVideo(
            source_id=source_id,
            item_index=1,
            title=_text(payload.get("title")) or source_id,
            cover_url=_text(payload.get("thumbnail")),
            duration_seconds=_positive_int(payload.get("duration")),
            source_url=source_url,
            provider=self._platform.provider,
        )


class YtDlpPlatformDownloader:
    """使用 yt-dlp 下载已解析的平台视频，并上报进度与取消状态。"""

    def __init__(self, platform: YtDlpPlatform) -> None:
        self._platform = platform

    def download(self, video: LinkedVideo, dest_dir: Path, reporter: ProgressReporter) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(dest_dir / f"{video.video_id}.%(ext)s")
        cookie_file = write_cookies_file(os.environ.get(self._platform.cookie_env, ""), self._platform.cookie_domain)
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--format",
            self._platform.format_selector,
            "--merge-output-format",
            "mp4",
            "--output",
            output_template,
            "--newline",
            "--add-header",
            f"User-Agent:{_DEFAULT_USER_AGENT}",
            *( ["--cookies", str(cookie_file)] if cookie_file is not None else [] ),
            video.source_url,
        ]
        try:
            reporter.update("download", 0.0, "开始下载")
            self._run_process(command, reporter)
            candidates = [
                path for path in sorted(dest_dir.glob(f"{video.video_id}.*"))
                if path.is_file() and not path.name.endswith(".part")
            ]
            if not candidates:
                raise RuntimeError(f"yt-dlp 下载完成但未找到输出文件：{video.video_id}.*")
            return candidates[0]
        except DownloadCancelled as error:
            reporter.cancelled(str(error))
            raise
        except Exception as error:
            platform_error = _external_platform_error(error, self._platform.display_name)
            reporter.failed(str(platform_error))
            raise platform_error from error
        finally:
            if cookie_file is not None:
                cookie_file.unlink(missing_ok=True)

    async def download_async(self, video: LinkedVideo, dest_dir: Path, reporter: ProgressReporter) -> Path:
        return await asyncio.to_thread(self.download, video, dest_dir, reporter)

    def _run_process(self, command: list[str], reporter: ProgressReporter) -> None:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if process.stdout is None:
            raise RuntimeError("无法读取 yt-dlp 输出。")
        recent_output: deque[str] = deque(maxlen=50)
        try:
            for line in process.stdout:
                stripped = line.rstrip()
                if stripped:
                    recent_output.append(stripped)
                if _is_cancelled(reporter):
                    process.terminate()
                    raise DownloadCancelled("下载已取消")
                match = _PROGRESS_RE.search(stripped)
                if match is not None:
                    reporter.update("download", float(match.group(1)), f"下载中 {match.group(1)}%")
            process.wait()
            if process.returncode != 0:
                detail = "\n".join(recent_output)
                raise RuntimeError(f"yt-dlp 退出码 {process.returncode}" + (f"；最近输出：\n{detail}" if detail else ""))
        except DownloadCancelled:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise


class BackgroundYtDlpDownloadStarter:
    def __init__(self, *, root_dir: Path, downloader: YtDlpPlatformDownloader, progress_tracker: ProgressTracker, on_downloaded: Callable[[str, str, Path], None] | None = None) -> None:
        self._root_dir = root_dir
        self._downloader = downloader
        self._progress_tracker = progress_tracker
        self._on_downloaded = on_downloaded

    def start_video(self, *, series_id: str, video: LinkedVideo) -> str:
        task_id = f"download/{series_id}/{video.video_id}"
        reporter = self._progress_tracker.create_reporter(task_id)

        async def run() -> None:
            try:
                path = await self._downloader.download_async(video, self._root_dir / "data" / "downloads" / series_id / video.video_id, reporter)
                if self._on_downloaded is None:
                    raise RuntimeError("A download sink is required; refusing to persist media outside BlobStore.")
                self._on_downloaded(series_id, video.video_id, path)
                reporter.completed(f"下载完成：{path.name}")
            except DownloadCancelled:
                return
            except ExternalVideoResolutionError:
                LOGGER.exception(
                    "linked video download failed",
                    extra={"event": "linked_video_download_failed", "provider": video.provider, "video_id": video.video_id},
                )
            except Exception:
                reporter.failed("下载完成后，媒体保存到工作区失败。请重试。")
                LOGGER.exception(
                    "linked video download persistence failed",
                    extra={"event": "linked_video_download_persistence_failed", "provider": video.provider, "video_id": video.video_id},
                )

        asyncio.create_task(run())
        return task_id


class YtDlpLinkedVideoDownloadStarter:
    def __init__(self, platform: YtDlpPlatform, starter: BackgroundYtDlpDownloadStarter) -> None:
        self._platform = platform
        self._starter = starter

    def start(self, *, series_id: str, video: LinkedVideo) -> str:
        if video.provider != self._platform.provider:
            raise RuntimeError(f"unsupported linked video provider '{video.provider}'")
        return self._starter.start_video(series_id=series_id, video=video)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _source_url(payload: Mapping[str, object], fallback_url: str) -> str:
    url = _text(payload.get("webpage_url")) or _text(payload.get("original_url")) or fallback_url
    return f"https:{url}" if url.startswith("//") else url


def _safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")


def _positive_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else 0


def _is_cancelled(reporter: ProgressReporter) -> bool:
    try:
        reporter.raise_if_cancelled()
    except RuntimeError:
        return True
    return False


def _external_platform_error(error: Exception, platform_name: str = "该平台") -> ExternalVideoResolutionError:
    message = str(error)
    normalized_message = message.lower()
    if (
        "fresh cookies" in normalized_message
        or "cookies are needed" in normalized_message
        or "cookies are no longer valid" in normalized_message
        or "sign in to confirm" in normalized_message
        or "not a bot" in normalized_message
    ):
        return ExternalVideoResolutionError("cookie_required", f"{platform_name} 需要重新验证登录状态。请重新获取 Cookie 后再试。")
    if "unsupported url" in normalized_message:
        return ExternalVideoResolutionError("invalid_url", "URL不合法，请输入合理的URL。")
    if "private video" in normalized_message or "login required" in normalized_message:
        return ExternalVideoResolutionError("cookie_required", f"{platform_name} 需要重新验证登录状态。请重新获取 Cookie 后再试。")
    if "http error 429" in normalized_message or "too many requests" in normalized_message:
        return ExternalVideoResolutionError("rate_limited", f"{platform_name} 暂时限制了下载请求，请稍后再试。")
    if "requested format is not available" in normalized_message or "no video formats" in normalized_message:
        return ExternalVideoResolutionError("format_unavailable", f"{platform_name} 未提供可下载的媒体格式，请稍后重试。")
    if "http error 403" in normalized_message or "forbidden" in normalized_message:
        return ExternalVideoResolutionError("access_denied", f"{platform_name} 拒绝了下载请求。请重新获取 Cookie 后再试。")
    if "timed out" in normalized_message or "network is unreachable" in normalized_message or "connection" in normalized_message:
        return ExternalVideoResolutionError("network_error", f"连接 {platform_name} 失败，请检查网络后重试。")
    if "unable to extract" in normalized_message or "signature extraction failed" in normalized_message or "nsig extraction failed" in normalized_message:
        return ExternalVideoResolutionError("extractor_outdated", f"{platform_name} 页面规则已变化，请更新 yt-dlp 后重试。")
    return ExternalVideoResolutionError("failed", f"{platform_name} 未能提供可下载的媒体。请稍后重试；若持续失败，请重新获取 Cookie。")


def _create_drission_page(user_data_dir: str, browser_port: int) -> object:
    try:
        from DrissionPage import Chromium, ChromiumOptions
    except ImportError as error:
        raise ExternalCookieInitError("当前 Python 环境缺少 DrissionPage，请先安装项目依赖。") from error
    options = ChromiumOptions(read_file=False).set_local_port(browser_port).set_user_data_path(user_data_dir)
    browser = Chromium(addr_or_opts=options)
    return _DrissionPageSession(browser, browser.latest_tab)


class _DrissionPageSession:
    def __init__(self, browser: object, page: object) -> None:
        self._browser = browser
        self._page = page

    def get(self, url: str) -> None:
        self._page.get(url)

    def cookies(self, *, all_domains: bool = True, all_info: bool = False) -> list[Mapping[str, object]]:
        return self._page.cookies(all_domains=all_domains, all_info=all_info)

    def quit(self) -> None:
        self._browser.quit()


def _page_get(page: object, url: str) -> None:
    getter = getattr(page, "get", None)
    if getter is None:
        raise ExternalCookieInitError("DrissionPage 页面对象缺少 get 方法。")
    getter(url)


def _page_cookies(page: object) -> list[Mapping[str, object]]:
    cookies = getattr(page, "cookies", None)
    if cookies is None:
        raise ExternalCookieInitError("DrissionPage 页面对象缺少 cookies 方法。")
    try:
        return cookies(all_domains=True, all_info=False)
    except TypeError:
        return cookies()


def _close_page(page: object) -> None:
    closer = getattr(page, "quit", None) or getattr(page, "close", None)
    if closer is not None:
        try:
            closer()
        except Exception:
            return


def _format_cookie_header(cookies: list[Mapping[str, object]], domain: str) -> str:
    pairs: list[str] = []
    seen: set[str] = set()
    for cookie in cookies:
        if domain not in str(cookie.get("domain", "")).lower():
            continue
        name = _text(cookie.get("name"))
        value = _text(cookie.get("value"))
        if name and value and name not in seen:
            pairs.append(f"{name}={value}")
            seen.add(name)
    return "; ".join(pairs)


def _has_login_cookie(cookie_header: str, names: tuple[str, ...]) -> bool:
    available_names = {name for name, _ in parse_cookie_pairs(cookie_header)}
    return any(name in available_names for name in names)


def _write_dotenv_value(dotenv_path: Path, key: str, value: str) -> None:
    lines = dotenv_path.read_text(encoding="utf-8").splitlines() if dotenv_path.exists() else []
    next_lines = [line for line in lines if not line.startswith(f"{key}=")]
    next_lines.append(f"{key}={value}")
    atomic_write_text(dotenv_path, "\n".join(next_lines).rstrip() + "\n")
