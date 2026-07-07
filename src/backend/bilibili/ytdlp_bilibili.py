"""Bilibili 视频的 yt-dlp 解析与下载适配器。

把 Bilibili 的视频/合集 URL 解析为库内可处理的 ``LinkedSeries`` /
``LinkedVideo`` 模型，并提供基于 yt-dlp 子进程的视频下载能力。
下载流程包含 B 站反爬头（UA/Referer/Cookie）、代理规避与进度上报。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.parse import parse_qsl, quote, urlparse

import httpx

try:
    import websocket
except ImportError:  # pragma: no cover - optional fallback dependency
    websocket = None

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.models import BilibiliUrlInfoDTO

_BILIBILI_USER_AGENT = "Mozilla/5.0"
_BILIBILI_COOKIE_ENV = "BILIBILI_COOKIE"
_BILIBILI_SESSDATA_ENV = "BILIBILI_SESSDATA"
_BILIBILI_COOKIE_BROWSER_ENV = "BILIBILI_COOKIE_BROWSER"
_BILINOTE_DOWNLOADER_COOKIE_FILE_ENV = "BILINOTE_DOWNLOADER_COOKIE_FILE"
BILIBILI_COOKIE_REQUIRED_MESSAGE = "风控拦截，请配置cookie"
EDGE_COOKIE_COPY_FAILED_MESSAGE = "无法读取 Edge Cookie，请关闭 Edge 浏览器后重试。"
_BILIBILI_LOGIN_URL = "https://passport.bilibili.com/login"
_BILIBILI_DEFAULT_BROWSER_PORT = 9223
_BILIBILI_QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_BILIBILI_QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


@dataclass(frozen=True)
class BiliNoteQrLoginSession:
    url: str
    qrcode_key: str


@dataclass(frozen=True)
class BiliNoteQrLoginPollResult:
    status: str
    message: str
    configured: bool = False


class ProgressReporter(Protocol):
    """下载进度的上报接口（Protocol）。

    由外部注入的 ``InMemoryProgressTracker`` 实现，通过 SSE 发送给前端。
    """

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None: ...
    def completed(self, detail: str | None = None) -> None: ...
    def failed(self, message: str) -> None: ...
    def cancelled(self, detail: str | None = None) -> None: ...
    def raise_if_cancelled(self) -> None: ...


class ProgressTracker(Protocol):
    """进度报告器的工厂端口（Protocol）。

    每次下载对应一个独立的 ``task_id``，创建对应的 ``ProgressReporter``。
    """

    def create_reporter(self, task_id: str) -> ProgressReporter: ...


class DownloadCancelled(RuntimeError):
    """下载被用户取消时抛出的异常。"""


class BilibiliCookieInitError(RuntimeError):
    """Bilibili Cookie 初始化失败。"""


class BiliNoteCookieConfigManager:
    """BiliNote 风格的平台 Cookie 持久化管理器。"""

    def __init__(self, filepath: str | Path = "config/downloader.json") -> None:
        self.path = Path(filepath)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict[str, dict[str, str]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        data: dict[str, dict[str, str]] = {}
        for platform, value in payload.items():
            if isinstance(platform, str) and isinstance(value, dict):
                cookie = value.get("cookie")
                if isinstance(cookie, str):
                    data[platform] = {"cookie": cookie}
        return data

    def _write(self, data: dict[str, dict[str, str]]) -> None:
        atomic_write_text(self.path, json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, platform: str) -> str | None:
        cookie = self._read().get(platform, {}).get("cookie")
        return cookie if cookie else None

    def set(self, platform: str, cookie: str) -> None:
        data = self._read()
        data[platform] = {"cookie": cookie}
        self._write(data)

    def delete(self, platform: str) -> None:
        data = self._read()
        if platform in data:
            del data[platform]
            self._write(data)

    def list_all(self) -> dict[str, str]:
        return {platform: value.get("cookie", "") for platform, value in self._read().items()}

    def exists(self, platform: str) -> bool:
        return self.get(platform) is not None


class YtDlpBilibiliResolver:
    """Bilibili URL 解析器——把 B 站链接解析为 ``LinkedSeries`` 或 ``LinkedVideo``。

    同时支持合集（多 P 系列、UGC Season）与单视频两种 URL 形态；
    解析流程：

    1. 调用 yt-dlp extract_info 获取元数据（flat 模式，仅标题/ID/时长）；
    2. 若标题缺失或为纯 BV 号，额外调用 Bilibili view API 补全标题；
    3. 从 view API 的 pages / ugc_season 中重建完整的 ``LinkedVideo`` 列表。

    关键不变量：extractor 注入后不可变；view API 仅在标题缺失时触发。
    """

    def __init__(
        self,
        extractor: Callable[[str], dict[str, object]] | None = None,
        view_extractor: Callable[[str], dict[str, object]] | None = None,
    ) -> None:
        self._extractor = extractor or _extract_info
        self._view_extractor = view_extractor or _extract_view_info

    async def resolve_series(self, url_info: BilibiliUrlInfoDTO) -> LinkedSeries:
        """将 Bilibili URL 解析为合集（LinkedSeries）。

        优先从 yt-dlp 的 ``entries`` 中获取视频列表；若 entries 为空或标题
        缺失（纯 BV 号），则调用 Bilibili view API 补全。

        Args:
            url_info: 包含归一化 URL 的 DTO。

        Returns:
            包含视频列表与系列元信息的 ``LinkedSeries``。
        """
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
        """将 Bilibili URL 解析为单个视频（LinkedVideo）。

        直接把 yt-dlp 返回的元数据映射为 ``LinkedVideo``，不触发 view API。

        Args:
            url_info: 包含归一化 URL 的 DTO。

        Returns:
            包含 BV 号、标题、时长、封面等信息的 ``LinkedVideo``。
        """
        payload = await asyncio.to_thread(self._extractor, url_info.url)
        return _linked_video_from_payload(payload, fallback_url=url_info.url)


class BilibiliDownloader:
    """Bilibili 视频下载器——通过 yt-dlp 子进程下载视频文件。

    下载策略（迭代演进到 v4）：
    - v1：无 User-Agent/Referer，B 站返回 412；
    - v2：加 UA/Referer/Cookie 头，但未关代理；
    - v3：加 ``--proxy ""``，但 Cookie 经 ``--add-header`` 注入会被 yt-dlp 的
      cookiejar 覆盖；
    - v4：Cookie 走 ``--cookies`` Netscape 文件，UA/Referer 走
      ``--add-header``；显式 ``--proxy ""`` 避免境内代理握手失败。

    视频质量：默认交由 yt-dlp 选择最佳 mp4 格式（``--merge-output-format mp4``）。
    """
    _PROGRESS_RE = re.compile(r"\[download\]\s+([\d.]+)%")

    def download(self, bvid: str, page: int, dest_dir: Path, reporter: ProgressReporter) -> Path:
        """同步下载单个 Bilibili 视频到指定目录。

        启动 yt-dlp 子进程，实时解析进度百分比并通过 ``reporter`` 上报；
        下载失败时收集最近 50 行输出拼入错误信息便于排错。

        Args:
            bvid: 视频的 BV 号。
            page: 分 P 页码（单 P 为 1）。
            dest_dir: 下载目标目录。
            reporter: 用于上报下载进度的报告器。

        Returns:
            下载完成的文件路径（``dest_dir`` 下第一个匹配 ``bvid.*`` 的文件）。

        Raises:
            DownloadCancelled: 下载过程中用户取消。
            RuntimeError: yt-dlp 退出码非 0 或下载完成后未找到输出文件。
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem = bvid if page == 1 else f"{bvid}_p{page}"
        url = f"https://www.bilibili.com/video/{bvid}"
        if page > 1:
            url = f"{url}?p={page}"
        output_template = str(dest_dir / f"{stem}.%(ext)s")
        headers = _load_bilibili_headers(bvid)
        cookie_file = _write_bilibili_cookies_file(headers.pop("Cookie", ""))
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
            "--proxy",
            "",
            *_build_yt_dlp_add_header_flags(headers),
            *(["--cookies", str(cookie_file)] if cookie_file is not None else []),
            url,
        ]
        reporter.update("download", 0.0, "开始下载")
        process = None
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
            output_tail: list[str] = []
            for line in process.stdout:
                stripped_line = line.rstrip()
                if stripped_line:
                    output_tail.append(stripped_line)
                    output_tail = output_tail[-20:]
                if _download_cancel_requested(reporter):
                    process.terminate()
                    raise DownloadCancelled("下载已取消")
                match = self._PROGRESS_RE.search(stripped_line)
                if match is None:
                    continue
                percent = float(match.group(1))
                if percent == last_percent:
                    continue
                last_percent = percent
                reporter.update("download", percent, f"下载中 {percent:.1f}%")
            process.wait()
            if process.returncode != 0:
                failure = _format_yt_dlp_failure(process.returncode, output_tail)
                if failure == BILIBILI_COOKIE_REQUIRED_MESSAGE:
                    browser_result = _download_bilibili_via_browser(bvid, page, dest_dir)
                    if browser_result is not None:
                        reporter.completed(f"下载完成：{browser_result.name}")
                        return browser_result
                raise RuntimeError(failure)
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
            if cookie_file is not None:
                cookie_file.unlink(missing_ok=True)

        candidates = sorted(dest_dir.glob(f"{stem}.*"))
        if not candidates:
            message = f"yt-dlp 下载完成但未找到输出文件：{stem}.*"
            reporter.failed(message)
            raise RuntimeError(message)
        reporter.completed(f"下载完成：{candidates[0].name}")
        return candidates[0]

    async def download_async(self, bvid: str, page: int, dest_dir: Path, reporter: ProgressReporter) -> Path:
        """异步包装 ``download``，避免阻塞事件循环。

        Args:
            bvid: 视频的 BV 号。
            page: 分 P 页码。
            dest_dir: 下载目标目录。
            reporter: 下载进度报告器。

        Returns:
            下载完成的文件路径。
        """
        return await asyncio.to_thread(self.download, bvid, page, dest_dir, reporter)


class DrissionBilibiliCookieInitializer:
    """通过 DrissionPage 打开 Bilibili 登录页并写入 BILIBILI_COOKIE。"""

    def __init__(
        self,
        *,
        root_dir: Path,
        page_factory: Callable[[str, int], object] | None = None,
        login_url: str = _BILIBILI_LOGIN_URL,
        browser_port: int = _BILIBILI_DEFAULT_BROWSER_PORT,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._root_dir = root_dir
        self._page_factory = page_factory or _create_drission_page
        self._login_url = login_url
        self._browser_port = browser_port
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds

    def init(self) -> bool:
        """打开 Bilibili 登录页，拿到登录 Cookie 后写入 .env 和当前进程环境。"""
        page = self._page_factory(str(self._root_dir / "data" / "bilibili" / "browser"), self._browser_port)
        try:
            _page_get(page, self._login_url)
            deadline = time.monotonic() + self._timeout_seconds
            while time.monotonic() <= deadline:
                cookie_header = _format_bilibili_cookie_header(_page_cookies(page))
                if _has_bilibili_login_cookie(cookie_header):
                    _write_dotenv_value(self._root_dir / ".env", _BILIBILI_COOKIE_ENV, cookie_header)
                    os.environ[_BILIBILI_COOKIE_ENV] = cookie_header
                    return True
                time.sleep(self._poll_interval_seconds)
            raise BilibiliCookieInitError("Bilibili 登录超时，未获取到 Cookie。")
        finally:
            _close_page(page)


class BiliNoteBilibiliCookieInitializer:
    """BiliNote 风格的 Bilibili Cookie 初始化器。"""

    def __init__(
        self,
        *,
        root_dir: Path,
        page_factory: Callable[[str, int], object] | None = None,
        login_url: str = _BILIBILI_LOGIN_URL,
        browser_port: int = _BILIBILI_DEFAULT_BROWSER_PORT,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
        cookie_config_path: Path | None = None,
    ) -> None:
        self._root_dir = root_dir
        self._page_factory = page_factory or _create_drission_page
        self._login_url = login_url
        self._browser_port = browser_port
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._cookie_config_path = cookie_config_path or root_dir / "config" / "downloader.json"

    def init(self, cookie: str | None = None) -> bool:
        if cookie is not None:
            cookie_header = cookie.strip()
            if not cookie_header:
                raise BilibiliCookieInitError("Bilibili Cookie 不能为空。")
            if _is_sessdata_only_cookie(cookie_header):
                raise BilibiliCookieInitError("请粘贴完整 Bilibili 浏览器 Cookie，不能只填写 SESSDATA。")
            self._save_cookie(cookie_header)
            return True

        page = self._page_factory(str(self._root_dir / "data" / "bilibili" / "browser"), self._browser_port)
        try:
            _page_get(page, self._login_url)
            deadline = time.monotonic() + self._timeout_seconds
            while time.monotonic() <= deadline:
                cookie_header = _format_bilibili_cookie_header(_page_cookies(page))
                if _has_bilibili_login_cookie(cookie_header):
                    self._save_cookie(cookie_header)
                    return True
                time.sleep(self._poll_interval_seconds)
            raise BilibiliCookieInitError("Bilibili 登录超时，未获取到 Cookie。")
        finally:
            _close_page(page)

    def _save_cookie(self, cookie: str) -> None:
        BiliNoteCookieConfigManager(self._cookie_config_path).set("bilibili", cookie)
        os.environ[_BILINOTE_DOWNLOADER_COOKIE_FILE_ENV] = str(self._cookie_config_path)
        os.environ.pop(_BILIBILI_COOKIE_ENV, None)
        os.environ.pop(_BILIBILI_SESSDATA_ENV, None)
        os.environ.pop(_BILIBILI_COOKIE_BROWSER_ENV, None)


class BiliNoteQrLoginService:
    """Bilibili 二维码登录服务，成功后写入 BiliNote Cookie 配置。"""

    def __init__(
        self,
        *,
        http_client_factory: Callable[[], object] | None = None,
        cookie_initializer: BiliNoteBilibiliCookieInitializer | None = None,
    ) -> None:
        self._http_client_factory = http_client_factory or (lambda: httpx.Client(timeout=20, headers={"User-Agent": _BILIBILI_USER_AGENT}))
        self._cookie_initializer = cookie_initializer
        self._clients: dict[str, object] = {}

    def create_session(self) -> BiliNoteQrLoginSession:
        client = self._http_client_factory()
        response = client.get(_BILIBILI_QR_GENERATE_URL)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get("url"), str) or not isinstance(data.get("qrcode_key"), str):
            _close_http_client(client)
            raise BilibiliCookieInitError("Bilibili 二维码生成失败。")
        qrcode_key = data["qrcode_key"]
        self._clients[qrcode_key] = client
        return BiliNoteQrLoginSession(url=data["url"], qrcode_key=qrcode_key)

    def poll(self, qrcode_key: str) -> BiliNoteQrLoginPollResult:
        client = self._clients.get(qrcode_key)
        if client is None:
            raise BilibiliCookieInitError("Bilibili 二维码会话不存在或已过期。")
        response = client.get(_BILIBILI_QR_POLL_URL, params={"qrcode_key": qrcode_key})
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise BilibiliCookieInitError("Bilibili 登录状态返回异常。")
        status_code = data.get("code")
        message = str(data.get("message") or "")
        if status_code == 0:
            try:
                cookie_header = _format_bilibili_cookie_header_from_items(client.cookies)
                poll_url = data.get("url")
                if isinstance(poll_url, str):
                    cookie_header = _merge_cookie_headers(cookie_header, _format_bilibili_cookie_header_from_url(poll_url))
                _supplement_bilibili_device_cookies(client, cookie_header)
                cookie_header = _merge_cookie_headers(cookie_header, _format_bilibili_cookie_header_from_items(client.cookies))
                initializer = self._cookie_initializer
                if initializer is None:
                    raise BilibiliCookieInitError("Bilibili Cookie 保存器未配置。")
                initializer.init(cookie_header)
                return BiliNoteQrLoginPollResult(status="confirmed", message=message or "扫码登录成功", configured=True)
            finally:
                self._clients.pop(qrcode_key, None)
                _close_http_client(client)
        if status_code == 86101:
            return BiliNoteQrLoginPollResult(status="waiting", message=message or "等待扫码")
        if status_code == 86090:
            return BiliNoteQrLoginPollResult(status="scanned", message=message or "已扫码，等待确认")
        self._clients.pop(qrcode_key, None)
        _close_http_client(client)
        return BiliNoteQrLoginPollResult(status="expired", message=message or "二维码已失效")


class EdgeBilibiliCookieInitializer:
    """把 Bilibili Cookie 来源配置为本机 Microsoft Edge。"""

    def __init__(self, *, root_dir: Path) -> None:
        self._root_dir = root_dir

    def init(self) -> bool:
        dotenv_path = self._root_dir / ".env"
        _write_dotenv_value(dotenv_path, _BILIBILI_COOKIE_ENV, "")
        _write_dotenv_value(dotenv_path, _BILIBILI_SESSDATA_ENV, "")
        _write_dotenv_value(dotenv_path, _BILIBILI_COOKIE_BROWSER_ENV, "edge")
        os.environ.pop(_BILIBILI_COOKIE_ENV, None)
        os.environ.pop(_BILIBILI_SESSDATA_ENV, None)
        os.environ[_BILIBILI_COOKIE_BROWSER_ENV] = "edge"
        return True


def build_video_download_task_id(series_id: str, video_id: str) -> str:
    """生成下载任务的唯一 ID，格式为 ``"download/{series_id}/{video_id}"``。

    Args:
        series_id: 系列 ID。
        video_id: 视频 ID。

    Returns:
        形如 ``"download/series-abc/video-xyz"`` 的任务 ID。
    """
    return f"download/{series_id}/{video_id}"


def _download_cancel_requested(reporter: ProgressReporter) -> bool:
    """检查 reporter 是否已触发取消信号。

    Args:
        reporter: 下载进度报告器。

    Returns:
        已取消则返回 ``True``，否则返回 ``False``。
    """
    try:
        reporter.raise_if_cancelled()
    except RuntimeError:
        return True
    return False


def _format_yt_dlp_failure(returncode: int, output_tail: list[str]) -> str:
    output = "\n".join(output_tail)
    if "HTTP Error 412" in output or "Precondition Failed" in output:
        return BILIBILI_COOKIE_REQUIRED_MESSAGE
    if "Could not copy Chrome cookie database" in output:
        return EDGE_COOKIE_COPY_FAILED_MESSAGE
    error_lines = [line for line in output_tail if "ERROR:" in line or "HTTP Error" in line]
    if error_lines:
        return error_lines[-1]
    return f"yt-dlp 退出码 {returncode}"


def _download_bilibili_via_browser(bvid: str, page: int, dest_dir: Path) -> Path | None:
    proxy_result = _download_bilibili_via_cdp_proxy(bvid, page, dest_dir)
    if proxy_result is not None:
        return proxy_result
    cdp_result = _download_bilibili_via_cdp(bvid, page, dest_dir)
    if cdp_result is not None:
        return cdp_result
    return _download_bilibili_via_drission(bvid, page, dest_dir)


def _download_bilibili_via_cdp_proxy(bvid: str, page: int, dest_dir: Path) -> Path | None:
    try:
        video_url = f"https://www.bilibili.com/video/{bvid}"
        if page > 1:
            video_url = f"{video_url}?p={page}"
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get("http://127.0.0.1:3456/new", params={"url": video_url})
            response.raise_for_status()
            target_id = response.json().get("targetId")
            if not isinstance(target_id, str) or not target_id:
                return None
            try:
                playinfo = _fetch_bilibili_browser_playinfo(client, target_id, bvid, page)
                media_url = playinfo.get("url")
                user_agent = playinfo.get("ua") or _BILIBILI_USER_AGENT
                referer = playinfo.get("referer") or video_url
                if not isinstance(media_url, str) or not media_url:
                    return None
                output_path = dest_dir / f"{bvid if page == 1 else f'{bvid}_p{page}'}.mp4"
                with client.stream(
                    "GET",
                    media_url,
                    headers={"User-Agent": str(user_agent), "Referer": str(referer)},
                    timeout=None,
                ) as media_response:
                    media_response.raise_for_status()
                    with output_path.open("wb") as output_file:
                        for chunk in media_response.iter_bytes():
                            if chunk:
                                output_file.write(chunk)
                return output_path if output_path.exists() else None
            finally:
                client.get("http://127.0.0.1:3456/close", params={"target": target_id})
    except Exception:
        return None


def _download_bilibili_via_cdp(bvid: str, page: int, dest_dir: Path) -> Path | None:
    if websocket is None:
        return None
    for browser_port in (9222, _BILIBILI_DEFAULT_BROWSER_PORT):
        result = _download_bilibili_via_cdp_port(bvid, page, dest_dir, browser_port)
        if result is not None:
            return result
    chrome_process = _start_temporary_cdp_chrome(_BILIBILI_DEFAULT_BROWSER_PORT)
    if chrome_process is None:
        return None
    try:
        _wait_for_cdp_port(_BILIBILI_DEFAULT_BROWSER_PORT)
        return _download_bilibili_via_cdp_port(bvid, page, dest_dir, _BILIBILI_DEFAULT_BROWSER_PORT)
    finally:
        _close_cdp_browser(_BILIBILI_DEFAULT_BROWSER_PORT)
        try:
            if chrome_process.poll() is None:
                chrome_process.terminate()
        except Exception:
            pass


def _download_bilibili_via_cdp_port(bvid: str, page: int, dest_dir: Path, browser_port: int) -> Path | None:
    video_url = f"https://www.bilibili.com/video/{bvid}"
    if page > 1:
        video_url = f"{video_url}?p={page}"
    target_id: str | None = None
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            client.get(f"http://127.0.0.1:{browser_port}/json/version").raise_for_status()
            target = client.put(f"http://127.0.0.1:{browser_port}/json/new?{quote(video_url, safe='')}")
            target.raise_for_status()
            target_payload = target.json()
            target_id = target_payload.get("id") if isinstance(target_payload, dict) else None
            ws_url = target_payload.get("webSocketDebuggerUrl") if isinstance(target_payload, dict) else None
            if not isinstance(target_id, str) or not isinstance(ws_url, str):
                return None
            cookie_header = _load_bilibili_headers(bvid).get("Cookie", "")
            playinfo = _fetch_bilibili_cdp_playinfo(ws_url, bvid, page, cookie_header)
            media_url = playinfo.get("url")
            user_agent = playinfo.get("ua") or _BILIBILI_USER_AGENT
            referer = playinfo.get("referer") or video_url
            if not isinstance(media_url, str) or not media_url:
                return None
            output_path = dest_dir / f"{bvid if page == 1 else f'{bvid}_p{page}'}.mp4"
            with client.stream(
                "GET",
                media_url,
                headers={"User-Agent": str(user_agent), "Referer": str(referer)},
                timeout=None,
            ) as media_response:
                media_response.raise_for_status()
                with output_path.open("wb") as output_file:
                    for chunk in media_response.iter_bytes():
                        if chunk:
                            output_file.write(chunk)
            return output_path if output_path.exists() else None
    except Exception:
        return None
    finally:
        if target_id:
            try:
                with httpx.Client(timeout=10) as client:
                    client.get(f"http://127.0.0.1:{browser_port}/json/close/{target_id}")
            except Exception:
                pass


def _start_temporary_cdp_chrome(browser_port: int) -> subprocess.Popen[bytes] | None:
    chrome_path = _find_chrome_executable()
    if not chrome_path:
        return None
    user_data_dir = Path(tempfile.gettempdir()) / "vsummary-bilibili-cdp-browser"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            chrome_path,
            f"--remote-debugging-port={browser_port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_cdp_port(browser_port: int, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{browser_port}/json/version", timeout=1)
            if response.status_code < 400:
                return
        except Exception:
            pass
        time.sleep(0.2)


def _find_chrome_executable() -> str | None:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "chrome",
        "msedge",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if candidate in {"chrome", "msedge"} or Path(candidate).exists():
            return candidate
    return None


def _close_cdp_browser(browser_port: int) -> None:
    if websocket is None:
        return
    try:
        response = httpx.get(f"http://127.0.0.1:{browser_port}/json/version", timeout=2)
        response.raise_for_status()
        payload = response.json()
        ws_url = payload.get("webSocketDebuggerUrl") if isinstance(payload, dict) else None
        if not isinstance(ws_url, str):
            return
        connection = websocket.create_connection(ws_url, timeout=5)
        try:
            _send_cdp_command(connection, 1, "Browser.close", {})
        finally:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
    except Exception:
        pass


def _download_bilibili_via_drission(bvid: str, page: int, dest_dir: Path) -> Path | None:
    video_url = f"https://www.bilibili.com/video/{bvid}"
    if page > 1:
        video_url = f"{video_url}?p={page}"
    for browser_port in (9222, _BILIBILI_DEFAULT_BROWSER_PORT):
        browser = None
        try:
            browser = _create_drission_page(str(Path.cwd() / "data" / "bilibili" / "browser"), browser_port)
            _page_get(browser, video_url)
            playinfo = _fetch_bilibili_drission_playinfo(browser, bvid, page)
            media_url = playinfo.get("url")
            user_agent = playinfo.get("ua") or _BILIBILI_USER_AGENT
            referer = playinfo.get("referer") or video_url
            if not isinstance(media_url, str) or not media_url:
                continue
            output_path = dest_dir / f"{bvid if page == 1 else f'{bvid}_p{page}'}.mp4"
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                with client.stream(
                    "GET",
                    media_url,
                    headers={"User-Agent": str(user_agent), "Referer": str(referer)},
                    timeout=None,
                ) as media_response:
                    media_response.raise_for_status()
                    with output_path.open("wb") as output_file:
                        for chunk in media_response.iter_bytes():
                            if chunk:
                                output_file.write(chunk)
            return output_path if output_path.exists() else None
        except Exception:
            continue
        finally:
            if browser is not None:
                _close_page(browser)
    return None


def _fetch_bilibili_browser_playinfo(client: httpx.Client, target_id: str, bvid: str, page: int) -> dict[str, object]:
    script = f"""
(async () => {{
  const bvid = {json.dumps(bvid)};
  const page = {page};
  const view = await fetch(`https://api.bilibili.com/x/web-interface/view?bvid=${{encodeURIComponent(bvid)}}`, {{
    credentials: 'include',
  }}).then(r => r.json());
  const pages = view.data && Array.isArray(view.data.pages) ? view.data.pages : [];
  const selected = pages[page - 1] || {{ cid: view.data && view.data.cid }};
  const params = new URLSearchParams({{ bvid, cid: String(selected.cid), fnval: '4048', qn: '32' }});
  const playinfo = await fetch(`https://api.bilibili.com/x/player/wbi/playurl?${{params.toString()}}`, {{
    credentials: 'include',
    headers: {{ Referer: location.href }},
  }}).then(r => r.json());
  const durl = playinfo.data && Array.isArray(playinfo.data.durl) ? playinfo.data.durl[0] : null;
  return JSON.stringify({{ url: durl && durl.url, size: durl && durl.size, ua: navigator.userAgent, referer: location.href }});
}})()
"""
    response = client.post("http://127.0.0.1:3456/eval", params={"target": target_id}, content=script)
    response.raise_for_status()
    payload = response.json()
    value = payload.get("value")
    if not isinstance(value, str):
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _fetch_bilibili_cdp_playinfo(ws_url: str, bvid: str, page: int, cookie_header: str = "") -> dict[str, object]:
    if websocket is None:
        return {}
    script = _build_bilibili_playinfo_script(bvid, page)
    connection = websocket.create_connection(ws_url, timeout=120)
    try:
        request_id = 1
        if cookie_header.strip():
            _send_cdp_command(connection, request_id, "Network.enable", {})
            request_id += 1
            _send_cdp_command(
                connection,
                request_id,
                "Network.setCookies",
                {"cookies": _cookie_header_to_cdp_cookies(cookie_header)},
            )
            request_id += 1
        request_id = _wait_for_cdp_page_ready(connection, request_id)
        result = _send_cdp_command(
            connection,
            request_id,
            "Runtime.evaluate",
            {
                "expression": script,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        runtime_result = result.get("result")
        if not isinstance(runtime_result, dict):
            return {}
        value = runtime_result.get("value")
        if not isinstance(value, str):
            return {}
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()


def _wait_for_cdp_page_ready(connection: object, request_id: int, timeout_seconds: float = 15.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        result = _send_cdp_command(
            connection,
            request_id,
            "Runtime.evaluate",
            {
                "expression": "`${location.href}|${document.readyState}`",
                "returnByValue": True,
            },
        )
        request_id += 1
        runtime_result = result.get("result")
        value = runtime_result.get("value") if isinstance(runtime_result, dict) else None
        if isinstance(value, str) and "|complete" in value and "bilibili.com/video/" in value:
            return request_id
        time.sleep(0.25)
    return request_id


def _send_cdp_command(connection: object, request_id: int, method: str, params: dict[str, object]) -> dict[str, object]:
    connection.send(json.dumps({"id": request_id, "method": method, "params": params}))
    while True:
        message = json.loads(connection.recv())
        if message.get("id") != request_id:
            continue
        result = message.get("result")
        return result if isinstance(result, dict) else {}


def _cookie_header_to_cdp_cookies(cookie_header: str) -> list[dict[str, object]]:
    cookies: list[dict[str, object]] = []
    for item in cookie_header.split(";"):
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".bilibili.com",
            "path": "/",
            "secure": True,
        })
    return cookies


def _fetch_bilibili_drission_playinfo(page_obj: object, bvid: str, page: int) -> dict[str, object]:
    script = _build_bilibili_playinfo_script(bvid, page)
    value = _page_run_js(page_obj, script)
    if not isinstance(value, str):
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _build_bilibili_playinfo_script(bvid: str, page: int) -> str:
    return f"""
(async () => {{
  const bvid = {json.dumps(bvid)};
  const page = {page};
  const view = await fetch(`https://api.bilibili.com/x/web-interface/view?bvid=${{encodeURIComponent(bvid)}}`, {{
    credentials: 'include',
  }}).then(r => r.json());
  const pages = view.data && Array.isArray(view.data.pages) ? view.data.pages : [];
  const selected = pages[page - 1] || {{ cid: view.data && view.data.cid }};
  const params = new URLSearchParams({{ bvid, cid: String(selected.cid), fnval: '4048', qn: '32' }});
  const playinfo = await fetch(`https://api.bilibili.com/x/player/wbi/playurl?${{params.toString()}}`, {{
    credentials: 'include',
    headers: {{ Referer: location.href }},
  }}).then(r => r.json());
  const durl = playinfo.data && Array.isArray(playinfo.data.durl) ? playinfo.data.durl[0] : null;
  return JSON.stringify({{ url: durl && durl.url, size: durl && durl.size, ua: navigator.userAgent, referer: location.href }});
}})()
"""


def _load_bilibili_headers(bvid: str) -> dict[str, str]:
    cookie = _load_bilinote_bilibili_cookie()
    if not cookie:
        cookie = os.environ.get(_BILIBILI_COOKIE_ENV, "").strip()
    if not cookie:
        sessdata = os.environ.get(_BILIBILI_SESSDATA_ENV, "").strip()
        cookie = f"SESSDATA={sessdata}" if sessdata else ""
    headers = {
        "User-Agent": _BILIBILI_USER_AGENT,
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _load_bilinote_bilibili_cookie() -> str:
    cookie_file = os.environ.get(_BILINOTE_DOWNLOADER_COOKIE_FILE_ENV, "").strip()
    manager = BiliNoteCookieConfigManager(cookie_file) if cookie_file else BiliNoteCookieConfigManager()
    return manager.get("bilibili") or ""


def _build_yt_dlp_add_header_flags(headers: dict[str, str]) -> list[str]:
    flags: list[str] = []
    for key, value in headers.items():
        if not value:
            continue
        flags.extend(["--add-header", f"{key}:{value}"])
    return flags


def _write_bilibili_cookies_file(cookie: str) -> Path | None:
    if not cookie.strip():
        return None
    cookie_pairs = _parse_cookie_pairs(cookie)
    if not cookie_pairs:
        return None
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".cookies.txt")
    with handle:
        handle.write("# Netscape HTTP Cookie File\n")
        for name, value in cookie_pairs:
            handle.write(f".bilibili.com\tTRUE\t/\tTRUE\t2147483647\t{name}\t{value}\n")
    return Path(handle.name)


def _parse_cookie_pairs(cookie: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        normalized_name = name.strip()
        normalized_value = value.strip()
        if normalized_name:
            pairs.append((normalized_name, normalized_value))
    return pairs


def _is_sessdata_only_cookie(cookie: str) -> bool:
    cookie_names = {name.lower() for name, _value in _parse_cookie_pairs(cookie)}
    if "sessdata" not in cookie_names:
        return False
    full_cookie_markers = {"buvid3", "buvid4", "bili_jct", "dedeuserid", "b_nut"}
    return cookie_names.isdisjoint(full_cookie_markers)


def _create_drission_page(user_data_dir: str, browser_port: int) -> object:
    try:
        from DrissionPage import Chromium, ChromiumOptions
    except ImportError as exc:
        raise BilibiliCookieInitError("当前 Python 环境缺少 DrissionPage，请先安装项目依赖。") from exc
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
        raise BilibiliCookieInitError("DrissionPage 页面对象缺少 get 方法。")
    getter(url)


def _page_cookies(page: object) -> list[Mapping[str, object]]:
    cookies = getattr(page, "cookies", None)
    if cookies is not None:
        try:
            return cookies(all_domains=True, all_info=False)
        except TypeError:
            return cookies()
    get_cookies = getattr(page, "get_cookies", None)
    if get_cookies is not None:
        return get_cookies(as_dict=False)
    raise BilibiliCookieInitError("DrissionPage 页面对象缺少 cookies 方法。")


def _page_run_js(page: object, script: str) -> object:
    runner = getattr(page, "run_js", None)
    if runner is not None:
        return runner(script)
    runner = getattr(page, "run_js_loaded", None)
    if runner is not None:
        return runner(script)
    raise BilibiliCookieInitError("DrissionPage 页面对象缺少 run_js 方法。")


def _close_page(page: object) -> None:
    for name in ("quit", "close"):
        method = getattr(page, name, None)
        if method is not None:
            method()
            return


def _format_bilibili_cookie_header(cookies: list[Mapping[str, object]]) -> str:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lower()
        if "bilibili.com" not in domain:
            continue
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        pairs.append((name, value))
    return "; ".join(f"{name}={value}" for name, value in pairs)


def _format_bilibili_cookie_header_from_items(cookies: object) -> str:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    jar = getattr(cookies, "jar", None)
    if jar is not None:
        iterable = ((cookie.name, cookie.value) for cookie in jar)
    else:
        items = getattr(cookies, "items", None)
        iterable = items() if callable(items) else cookies
    for name, value in iterable:
        cookie_name = str(name).strip()
        cookie_value = str(value).strip()
        if not cookie_name or cookie_name in seen:
            continue
        seen.add(cookie_name)
        pairs.append((cookie_name, cookie_value))
    return "; ".join(f"{name}={value}" for name, value in pairs)


def _format_bilibili_cookie_header_from_url(url: str) -> str:
    return _format_bilibili_cookie_header_from_items(parse_qsl(urlparse(url).query, keep_blank_values=True))


def _merge_cookie_headers(*headers: str) -> str:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for header in headers:
        for name, value in _parse_cookie_pairs(header):
            if name in seen:
                continue
            seen.add(name)
            pairs.append((name, value))
    return "; ".join(f"{name}={value}" for name, value in pairs)


def _supplement_bilibili_device_cookies(client: object, cookie_header: str) -> None:
    get = getattr(client, "get", None)
    if get is None:
        return
    try:
        get("https://www.bilibili.com/", headers={"Cookie": cookie_header, "Referer": "https://www.bilibili.com/"})
        response = get(
            "https://api.bilibili.com/x/frontend/finger/spi",
            headers={"Cookie": cookie_header, "Referer": "https://www.bilibili.com/"},
        )
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return
        cookies = getattr(client, "cookies", None)
        update = getattr(cookies, "update", None)
        if update is None:
            return
        device_cookies = {}
        if isinstance(data.get("b_3"), str):
            device_cookies["buvid3"] = data["b_3"]
        if isinstance(data.get("b_4"), str):
            device_cookies["buvid4"] = data["b_4"]
        if device_cookies:
            update(device_cookies)
    except Exception:
        return


def _close_http_client(client: object) -> None:
    close = getattr(client, "close", None)
    if close is not None:
        close()


def _has_bilibili_login_cookie(cookie_header: str) -> bool:
    names = {name for name, _ in _parse_cookie_pairs(cookie_header)}
    return "SESSDATA" in names


def _write_dotenv_value(dotenv_path: Path, key: str, value: str) -> None:
    lines = dotenv_path.read_text(encoding="utf-8").splitlines() if dotenv_path.exists() else []
    next_lines: list[str] = []
    replaced = False
    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or "=" not in raw_line:
            next_lines.append(raw_line)
            continue
        raw_key, _ = raw_line.split("=", 1)
        if raw_key.strip() == key:
            next_lines.append(f"{key}={value}")
            replaced = True
        else:
            next_lines.append(raw_line)
    if not replaced:
        next_lines.append(f"{key}={value}")
    atomic_write_text(dotenv_path, "\n".join(next_lines).rstrip() + "\n")


class BackgroundBilibiliDownloadStarter:
    """后台 Bilibili 下载启动器——创建 asyncio 后台任务执行下载。

    下载在后台线程中运行（通过 ``asyncio.to_thread``），不阻塞调用方；
    返回一个可被前端通过 SSE 订阅进度的 ``task_id``。
    """
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
        """在后台启动指定 Bilibili 视频的下载。

        创建 asyncio 后台任务；成功返回 ``task_id``，失败由 reporter 上报。

        Args:
            series_id: 系列 ID。
            video_id: 视频 ID。
            bvid: 视频的 BV 号。
            page: 分 P 页码。

        Returns:
            可被前端订阅的下载任务 ID。
        """
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
        """从 ``LinkedVideo`` 对象提取字段后启动后台下载。

        Args:
            series_id: 系列 ID。
            video: 包含 ``bvid``、``page``、``video_id`` 的 ``LinkedVideo``。

        Returns:
            下载任务 ID。
        """
        return self.start(series_id=series_id, video_id=video.video_id, bvid=video.bvid, page=video.page)


class BilibiliLinkedVideoDownloadStarter:
    """Bilibili 专用下载启动器的适配层。

    校验 ``video.provider == "bilibili"`` 后委托给
    ``BackgroundBilibiliDownloadStarter``。
    """

    def __init__(self, starter: BackgroundBilibiliDownloadStarter) -> None:
        self._starter = starter

    def start(self, *, series_id: str, video) -> str:
        """根据 provider 路由到 Bilibili 下载启动器。

        Args:
            series_id: 系列 ID。
            video: 链接型视频对象。

        Returns:
            下载任务 ID。

        Raises:
            RuntimeError: provider 不是 ``"bilibili"``。
        """
        if video.provider != "bilibili":
            raise RuntimeError(f"unsupported linked video provider '{video.provider}'")
        return self._starter.start_video(series_id=series_id, video=video)


class CompositeLinkedVideoDownloadStarter:
    """多 provider 下载的复合启动器——按 ``video.provider`` 分发到对应启动器。

    同时支持 Bilibili、Chaoxing 等多种外部来源；新的 provider 只需在
    ``starters`` 字典中注册即可。
    """

    def __init__(self, starters: dict[str, object]) -> None:
        self._starters = starters

    def start(self, *, series_id: str, video) -> str:
        """根据 ``video.provider`` 路由到对应的下载启动器。

        Args:
            series_id: 系列 ID。
            video: 链接型视频对象。

        Returns:
            下载任务 ID。

        Raises:
            RuntimeError: provider 在 ``starters`` 中未注册。
        """
        starter = self._starters.get(video.provider)
        if starter is None:
            raise RuntimeError(f"unsupported linked video provider '{video.provider}'")
        return starter.start(series_id=series_id, video=video)


def _extract_info(url: str) -> dict[str, object]:
    """通过 yt-dlp 提取 Bilibili URL 的元数据（flat 模式，不下载）。

    使用 ``extract_flat: "in_playlist"`` 仅获取合集下的标题、ID、时长等
    元信息，不递归下载每个视频的完整信息。

    Args:
        url: Bilibili 视频或合集 URL。

    Returns:
        yt-dlp 返回的元数据字典。

    Raises:
        RuntimeError: yt-dlp 返回的不是有效 dict。
    """
    from yt_dlp import YoutubeDL

    bvid = _extract_bvid_from_text(url)
    headers = _load_bilibili_headers(bvid) if bvid else {
        "User-Agent": _BILIBILI_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
    }
    cookie_file = _write_bilibili_cookies_file(headers.pop("Cookie", ""))
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "proxy": "",
        "http_headers": headers,
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


def _extract_view_info(bvid: str) -> dict[str, object]:
    """调用 Bilibili View API 获取视频的详细信息。

    显式 ``proxy=None`` 避免境内 API 的 TLS 代理握手失败（
    SSL: UNEXPECTED_EOF_WHILE_READING）。

    Args:
        bvid: 视频的 BV 号。

    Returns:
        View API 响应中的 ``data`` 字段。

    Raises:
        RuntimeError: API 返回异常（code != 0 或 data 无效）。
    """
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
    """从 yt-dlp 元数据中提取 BV 号并异步调用 View API 补全详情。

    Args:
        payload: yt-dlp 返回的元数据。
        fallback_url: 提取 BV 号失败时用于正则匹配的备选 URL。
        view_extractor: 调 View API 的回调。

    Returns:
        ``(bvid, view_data)`` 元组；BV 号提取失败则返回 ``("", {})``。
    """
    try:
        bvid = _extract_bvid(payload)
    except ValueError:
        bvid = _extract_bvid_from_entries(payload) or _extract_bvid_from_text(fallback_url)
        if not bvid:
            return "", {}
    return bvid, await asyncio.to_thread(view_extractor, bvid)


def _linked_video_from_payload(payload: dict[str, object], *, fallback_url: str) -> LinkedVideo:
    """将 yt-dlp 的元数据 dict 映射为 ``LinkedVideo`` 对象。

    自动从 ``id``/``display_id``/``webpage_url``/``url`` 中提取 BV 号，
    从 ``page_number``/``playlist_index``/URL 中提取分 P 页码。

    Args:
        payload: yt-dlp 返回的元数据字典。
        fallback_url: 提取 URL 失败时的备选地址。

    Returns:
        结构化的 ``LinkedVideo`` 对象。
    """
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
    """判断是否需要调用 View API 补全标题。

    当 yt-dlp 返回的标题是纯 BV 号或任意 entry 缺少标题时触发。

    Args:
        payload: yt-dlp 元数据。
        entries: 已解析的视频条目列表。

    Returns:
        需要补全标题则返回 ``True``。
    """
    if _is_bvid_title(_as_text(payload.get("title"))):
        return True
    return any(not _as_text(entry.get("title")) or _is_bvid_title(_as_text(entry.get("title"))) for entry in entries)


def _entries_from_view_payload(*, view_bvid: str, view_payload: dict[str, object]) -> list[dict[str, object]]:
    """从 View API 返回的 data 中重建视频条目列表。

    优先从 ``ugc_season.sections.episodes`` 提取，回退到 ``pages`` 数组。

    Args:
        view_bvid: 根 BV 号。
        view_payload: View API 返回的 data 字典。

    Returns:
        标准化的条目列表（每项含 id/title/page_number/duration/thumbnail/webpage_url）。
    """
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
    """从 UGC Season 对象中提取所有分集信息。

    遍历 ``sections → episodes`` 两级结构，提取每集的 BV 号、标题、
    时长、封面。

    Args:
        season: View API 返回的 ``ugc_season`` 字典。

    Returns:
        标准化条目列表；不包含 BV 号的条目会被跳过。
    """
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
    """用 View API 补全的标题覆盖 yt-dlp 条目中的标题。

    Args:
        entry: yt-dlp 元数据条目。
        title_overrides: 从 ``_extract_title_overrides`` 得到的
            ``(bvid, page) → title`` 映射。

    Returns:
        标题已覆盖的新条目 dict；若无匹配的覆盖则返回原条目。
    """
    bvid = _extract_bvid(entry)
    page = _extract_page(entry)
    current_title = _as_text(entry.get("title"))
    override = title_overrides.get((bvid, page)) or title_overrides.get((bvid, 1))
    if not override:
        return entry
    return {**entry, "title": override}


def _extract_title_overrides(view_payload: dict[str, object], *, root_bvid: str) -> dict[tuple[str, int], str]:
    """从 View API 的 pages/ugc_season 中提取标题覆盖映射。

    Args:
        view_payload: View API 返回的 data 字典。
        root_bvid: 根 BV 号。

    Returns:
        ``{(bvid, page): title}`` 映射字典。
    """
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
    """根据 BV 号和分 P 页码构造 Bilibili 视频页面 URL。

    Args:
        bvid: 视频 BV 号。
        page: 分 P 页码，1 时不追加 ``?p=``。

    Returns:
        形如 ``"https://www.bilibili.com/video/BVxxx"`` 或带 ``?p=N`` 的 URL。
    """
    url = f"https://www.bilibili.com/video/{bvid}"
    return f"{url}?p={page}" if page > 1 else url


def _extract_series_title(view_payload: dict[str, object]) -> str:
    """从 View API 数据中提取系列（合集）标题。

    优先取 ``ugc_season.title``，回退到顶层 ``title``。

    Args:
        view_payload: View API 返回的 data 字典。

    Returns:
        系列标题字符串；若均无则返回空字符串。
    """
    season = view_payload.get("ugc_season")
    if isinstance(season, dict):
        title = _as_text(season.get("title"))
        if title:
            return title
    return _as_text(view_payload.get("title"))


def _extract_bvid(payload: dict[str, object]) -> str:
    """从 yt-dlp 元数据中提取 Bilibili BV 号。

    依次在 ``id``、``display_id``、``webpage_url``、``url`` 字段中
    用正则匹配 BV 号（``BV[0-9A-Za-z]{10}``）。

    Args:
        payload: yt-dlp 元数据字典。

    Returns:
        BV 号字符串（如 ``"BV1xx411c7mD"``）。

    Raises:
        ValueError: 所有候选字段均未找到 BV 号。
    """
    candidates = [payload.get("id"), payload.get("display_id"), payload.get("webpage_url"), payload.get("url")]
    for value in candidates:
        bvid = _extract_bvid_from_text(str(value or ""))
        if bvid:
            return bvid
    raise ValueError("yt-dlp 元数据中缺少 Bilibili BV 号。")


def _extract_bvid_from_entries(payload: dict[str, object]) -> str:
    """遍历 yt-dlp 的 entries 列表，尝试从第一项中提取 BV 号。

    Args:
        payload: yt-dlp 元数据。

    Returns:
        提取到的 BV 号；全部失败则返回空字符串。
    """
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
    """用正则从任意文本中提取 Bilibili BV 号（``BV[0-9A-Za-z]{10}``）。

    Args:
        value: 任意文本（URL、字符串等）。

    Returns:
        BV 号字符串；未匹配则返回空字符串。
    """
    match = re.search(r"(BV[a-zA-Z0-9]{10})", value)
    return match.group(1) if match else ""


def _extract_page(payload: dict[str, object]) -> int:
    """从 yt-dlp 元数据中提取分 P 页码。

    依次查找 ``page_number``、``playlist_index`` 字段，
    再回退到 URL 中正则匹配 ``?p=N`` 参数。

    Args:
        payload: yt-dlp 元数据。

    Returns:
        页码（最小为 1）。
    """
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
    """从 URL 或文本中正则提取 ``?p=N`` / ``&p=N`` 的分 P 页码。

    Args:
        value: 任意文本。

    Returns:
        页码；未匹配则返回 0。
    """
    match = re.search(r"(?:[?&]p=)(\d+)", value)
    if match is None:
        return 0
    return int(match.group(1))


def _as_positive_int(value: object, fallback: int) -> int:
    """安全地将值转为正整数，bool 和 <=0 的值返回 ``fallback``。

    Args:
        value: 待转换的值。
        fallback: 转换失败或值 <=0 时的默认值。

    Returns:
        正整数或 fallback。
    """
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return fallback


def _is_bvid_title(value: str) -> bool:
    """判断一个字符串是否恰好是 Bilibili BV 号（或 BV 号 + ``_pN`` 后缀）。

    Args:
        value: 待判断的字符串。

    Returns:
        是 BV 号则返回 ``True``。
    """
    return bool(re.fullmatch(r"BV[a-zA-Z0-9]{10}(?:_p\d+)?", value.strip()))


def _safe_series_key(value: str) -> str:
    """将任意字符串转为合法的系列键（仅保留字母数字、连字符和下划线）。

    Args:
        value: 原始字符串。

    Returns:
        清理后的键；完全为空时返回 ``"linked-series"``。
    """
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return normalized or "linked-series"


def _as_text(value: object) -> str:
    """安全地将值转为字符串，非 str 返回空字符串。

    Args:
        value: 待转换的值。

    Returns:
        str 则去空白后返回，其它类型返回 ``""``。
    """
    return value.strip() if isinstance(value, str) else ""


def _as_int(value: object) -> int:
    """安全地将值转为非负整数，bool 和负数均返回 0。

    Args:
        value: 待转换的值。

    Returns:
        非负整数值。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0
