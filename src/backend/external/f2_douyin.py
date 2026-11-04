"""通过 F2（Johnserf-Seed/f2）解析和下载抖音单个视频。

yt-dlp 请求抖音接口时常被风控拒绝（报需要 fresh cookies）；F2 自带 a_bogus 签名。这里只借用 F2
发出带签名的作品详情请求，播放地址由本模块自己下载。

F2 在导入 ``f2.apps.douyin.model`` 时就会联网获取 msToken，所以只在真正解析时于工作线程中导入，
绝不能在应用启动时导入。F2 声明的依赖版本与本项目冲突，需用 ``pip install --no-deps`` 安装
（见 requirements.nodeps.txt）。
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx

from backend.external.ytdlp import (
    DOUYIN_PLATFORM,
    DownloadCancelled,
    ExternalVideoResolutionError,
    ProgressReporter,
    douyin_aweme_id,
    resolve_douyin_video_url,
)
from backend.shared.request_pacing import RequestPacer
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


LOGGER = logging.getLogger(__name__)

F2_MISSING_MESSAGE = (
    "抖音解析方式为 F2，但当前环境没有安装 F2。请运行 pip install --no-deps -r requirements.nodeps.txt，"
    "或在 config/settings.toml 的 [external_import.douyin] 中把 source 改为 \"ytdlp\"。"
)
_COOKIE_REQUIRED = "抖音需要登录 Cookie，请先点「获取 Cookie」登录后再试。"
_NOT_RETURNED = "抖音没有返回这个作品：可能已删除、设为私密，或 Cookie 已失效。请重新获取 Cookie 后再试。"
_REFERER = "https://www.douyin.com/"
_FALLBACK_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

_f2_lock = Lock()
_f2: SimpleNamespace | None = None


def _load_f2() -> SimpleNamespace:
    global _f2
    with _f2_lock:
        if _f2 is None:
            # F2's logger writes a new file under ./logs on import unless its loggers already have a
            # handler; give them one so its records go through our logging instead.
            for name in ("f2", "f2-trace"):
                f2_logger = logging.getLogger(name)
                if not f2_logger.handlers:
                    f2_logger.addHandler(logging.NullHandler())
            # Importing F2 fires several token requests that each wait out their timeouts and retries
            # (over two minutes offline); fail fast when Douyin is unreachable at all.
            _require_douyin_reachable()
            try:
                from f2.apps.douyin.crawler import DouyinCrawler
                from f2.apps.douyin.model import PostDetail
                from f2.apps.douyin.utils import ClientConfManager
            except ModuleNotFoundError as error:
                raise ExternalVideoResolutionError("f2_unavailable", F2_MISSING_MESSAGE) from error
            except Exception as error:
                # The msToken request runs during import; a failure here is a network problem.
                raise ExternalVideoResolutionError("network_error", "连接抖音失败，请检查网络后重试。") from error
            _f2 = SimpleNamespace(DouyinCrawler=DouyinCrawler, PostDetail=PostDetail,
                headers=dict(ClientConfManager.headers()))
        return _f2


def _require_douyin_reachable() -> None:
    request = Request(_REFERER, method="HEAD", headers={"User-Agent": _FALLBACK_USER_AGENT})
    try:
        with urlopen(request, timeout=8):
            pass
    except HTTPError:
        return  # Any HTTP answer means the site is reachable.
    except (URLError, TimeoutError, OSError) as error:
        raise ExternalVideoResolutionError("network_error", "连接抖音失败，请检查网络后重试。") from error


DetailFetcher = Callable[[str, str], Awaitable[dict]]


async def _fetch_with_f2(aweme_id: str, cookie: str) -> dict:
    f2 = await asyncio.to_thread(_load_f2)
    kwargs = {"headers": f2.headers, "cookie": cookie, "proxies": _environment_proxies(), "timeout": 15, "max_retries": 2}
    async with f2.DouyinCrawler(kwargs) as crawler:
        return await crawler.fetch_post_detail(f2.PostDetail(aweme_id=aweme_id))


class F2DouyinClient:
    """用 F2 的签名请求作品详情，返回原始 JSON 中的 ``aweme_detail``。"""

    def __init__(self, *, request_pacer: RequestPacer | None = None, cookie: str | None = None,
        detail_fetcher: DetailFetcher | None = None) -> None:
        self._request_pacer = request_pacer
        self._cookie = cookie
        self._detail_fetcher = detail_fetcher or _fetch_with_f2

    @property
    def cookie(self) -> str:
        return (self._cookie if self._cookie is not None else os.environ.get(DOUYIN_PLATFORM.cookie_env, "")).strip()

    @property
    def user_agent(self) -> str:
        return (_f2.headers.get("User-Agent") if _f2 is not None else None) or _FALLBACK_USER_AGENT

    async def fetch_detail(self, aweme_id: str) -> dict:
        cookie = self.cookie
        if not cookie:
            raise ExternalVideoResolutionError("cookie_required", _COOKIE_REQUIRED)
        if self._request_pacer is not None:
            await asyncio.to_thread(self._request_pacer.wait)
        try:
            payload = await self._detail_fetcher(aweme_id, cookie)
        except ExternalVideoResolutionError:
            raise
        except Exception as error:
            LOGGER.warning("F2 douyin detail request failed for %s: %s", aweme_id, error)
            if isinstance(error, (TimeoutError, ConnectionError, httpx.TransportError)) or "timeout" in type(error).__name__.lower():
                raise ExternalVideoResolutionError("network_error", "连接抖音失败，请检查网络后重试。") from error
            raise ExternalVideoResolutionError("failed", "抖音未能返回作品信息，请稍后重试；若持续失败，请重新获取 Cookie。") from error
        detail = payload.get("aweme_detail") if isinstance(payload, dict) else None
        if not isinstance(detail, dict):
            raise ExternalVideoResolutionError("cookie_required", _NOT_RETURNED)
        return detail


class F2DouyinResolver:
    """把抖音单个视频链接解析为链接视频；合集与图文作品给出明确提示。"""

    def __init__(self, client: F2DouyinClient, *, redirect_follower: Callable[[str], str] | None = None) -> None:
        self._client = client
        self._redirect_follower = redirect_follower

    async def resolve_single_video(self, url_info) -> LinkedVideo:
        url = await asyncio.to_thread(resolve_douyin_video_url, url_info.url, redirect_follower=self._redirect_follower)
        aweme_id = douyin_aweme_id(url)
        if aweme_id is None:
            raise ExternalVideoResolutionError("invalid_url", "抖音的这种链接暂不支持解析，请粘贴单个视频的链接。")
        return _to_video(await self._client.fetch_detail(aweme_id), aweme_id)

    async def resolve_series(self, url_info) -> LinkedSeries:
        video = await self.resolve_single_video(url_info)
        return LinkedSeries(series_id=f"douyin-{video.source_id}", title=video.title, cover_url=video.cover_url,
            source_url=video.source_url, videos=[video])


class F2DouyinDownloader:
    """下载时重新取一次作品详情（播放地址会过期），再直接下载 MP4。"""

    def __init__(self, client: F2DouyinClient, *, max_height: int | None = None,
        http_client_factory: Callable[..., httpx.Client] = httpx.Client) -> None:
        self._client = client
        self._max_height = max_height
        self._http_client_factory = http_client_factory

    def download(self, video: LinkedVideo, dest_dir: Path, reporter: ProgressReporter) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / f"{video.video_id}.mp4"
        partial = dest_dir / f"{video.video_id}.mp4.part"
        try:
            reporter.update("download", 0.0, "开始下载")
            if _reporter_cancelled(reporter):
                raise DownloadCancelled("下载已取消")
            aweme_id = douyin_aweme_id(video.source_url) or video.source_id
            detail = asyncio.run(self._client.fetch_detail(aweme_id))
            self._stream(_play_urls(detail, self._max_height), partial, reporter)
            partial.replace(target)
            return target
        except DownloadCancelled as error:
            reporter.cancelled(str(error))
            raise
        except ExternalVideoResolutionError as error:
            reporter.failed(str(error))
            raise
        except Exception as error:
            if _is_cancel(error):
                reporter.cancelled("下载已取消")
                raise DownloadCancelled("下载已取消") from error
            LOGGER.warning("F2 douyin download failed for %s: %s", video.source_url, error)
            failure = ExternalVideoResolutionError("failed", "抖音视频下载失败，请稍后重试；若持续失败，请重新获取 Cookie。")
            reporter.failed(str(failure))
            raise failure from error
        finally:
            partial.unlink(missing_ok=True)

    async def download_async(self, video: LinkedVideo, dest_dir: Path, reporter: ProgressReporter) -> Path:
        return await asyncio.to_thread(self.download, video, dest_dir, reporter)

    def _stream(self, urls: list[str], partial: Path, reporter: ProgressReporter) -> None:
        headers = {"User-Agent": self._client.user_agent, "Referer": _REFERER, "Cookie": self._client.cookie}
        last_error: Exception | None = None
        with self._http_client_factory(headers=headers, follow_redirects=True, timeout=30) as client:
            for url in urls:
                try:
                    with client.stream("GET", url) as response:
                        response.raise_for_status()
                        total = int(response.headers.get("Content-Length") or 0)
                        received, reported = 0, -1
                        with partial.open("wb") as output:
                            for chunk in response.iter_bytes(1 << 16):
                                if _reporter_cancelled(reporter):
                                    raise DownloadCancelled("下载已取消")
                                output.write(chunk)
                                received += len(chunk)
                                percent = int(received * 100 / total) if total else -1
                                if percent > reported:
                                    reported = percent
                                    reporter.update("download", float(percent), f"下载中 {percent}%")
                    if partial.stat().st_size == 0:
                        raise RuntimeError("抖音返回了空文件")
                    return
                except DownloadCancelled:
                    raise
                except Exception as error:
                    last_error = error
        raise RuntimeError(f"所有播放地址都下载失败：{last_error}")


def _to_video(detail: dict, aweme_id: str) -> LinkedVideo:
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    if detail.get("images") and not _play_urls(detail, None, strict=False):
        raise ExternalVideoResolutionError("invalid_url", "这是抖音图文作品，没有可以转写的视频。")
    description = str(detail.get("desc") or detail.get("caption") or "").strip()
    title = next((line.strip() for line in description.splitlines() if line.strip()), "") or aweme_id
    duration_ms = detail.get("duration") or video.get("duration") or 0
    return LinkedVideo(
        source_id=str(detail.get("aweme_id") or aweme_id),
        item_index=1,
        title=title[:120],
        cover_url=_first_url(video.get("origin_cover")) or _first_url(video.get("cover")),
        duration_seconds=round(duration_ms / 1000) if isinstance(duration_ms, (int, float)) and duration_ms > 0 else 0,
        source_url=f"https://www.douyin.com/video/{aweme_id}",
        provider="douyin",
    )


def _play_urls(detail: dict, max_height: int | None, *, strict: bool = True) -> list[str]:
    """Candidate MP4 URLs: H.264 before H.265 (browsers play it), then highest bit rate within the height cap."""
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    variants = []
    for item in video.get("bit_rate") or ():
        address = item.get("play_addr") if isinstance(item, dict) else None
        urls = list(address.get("url_list") or ()) if isinstance(address, dict) else []
        if not urls:
            continue
        height = address.get("height") or 0
        if max_height is not None and height and height > max_height:
            continue
        variants.append(((1 if item.get("is_h265") else 0, -(item.get("bit_rate") or 0)), urls))
    urls = [url for _, group in sorted(variants, key=lambda pair: pair[0]) for url in group]
    fallback = video.get("play_addr")
    if isinstance(fallback, dict):
        urls.extend(url for url in fallback.get("url_list") or () if url not in urls)
    if not urls and strict:
        raise ExternalVideoResolutionError("format_unavailable", "抖音没有提供可下载的视频地址，请稍后重试。")
    return urls


def _first_url(image: object) -> str:
    urls = image.get("url_list") if isinstance(image, dict) else None
    return str(urls[0]) if urls else ""


def _environment_proxies() -> dict[str, str | None]:
    return {
        "http://": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None,
        "https://": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None,
    }


def _reporter_cancelled(reporter: ProgressReporter) -> bool:
    try:
        reporter.raise_if_cancelled()
    except Exception:
        return True
    return False


def _is_cancel(error: Exception) -> bool:
    return isinstance(error, InterruptedError) or "cancel" in type(error).__name__.lower()
