from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from backend.external.f2_douyin import F2DouyinClient, F2DouyinDownloader, F2DouyinResolver
from backend.external.ytdlp import ExternalVideoResolutionError
from backend.video_summary.infrastructure.config.settings import load_settings

AWEME_ID = "7688297585299863141"
DETAIL = {
    "aweme_id": AWEME_ID,
    "desc": "第一行是标题\n#话题 #标签",
    "duration": 61_500,
    "video": {
        "origin_cover": {"url_list": ["https://cover.example/origin.jpg"]},
        "bit_rate": [
            {"bit_rate": 2_000_000, "is_h265": 1, "play_addr": {"height": 1080, "url_list": ["https://cdn.example/h265.mp4"]}},
            {"bit_rate": 1_200_000, "is_h265": 0, "play_addr": {"height": 1080, "url_list": ["https://cdn.example/h264-1080.mp4"]}},
            {"bit_rate": 600_000, "is_h265": 0, "play_addr": {"height": 480, "url_list": ["https://cdn.example/h264-480.mp4"]}},
        ],
    },
}


class _UrlInfo:
    def __init__(self, url: str) -> None:
        self.url = url


class _Reporter:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def update(self, stage, progress=None, detail=None):
        self.events.append((stage, progress))

    def completed(self, detail=None): ...
    def failed(self, message): self.events.append(("failed", message))
    def cancelled(self, detail=None): self.events.append(("cancelled", detail))
    def raise_if_cancelled(self): ...


def _client(requested: list[str] | None = None, cookie: str = "sessionid=abc") -> F2DouyinClient:
    async def fetch(aweme_id: str, _cookie: str) -> dict:
        (requested if requested is not None else []).append(aweme_id)
        return {"aweme_detail": DETAIL}
    return F2DouyinClient(cookie=cookie, detail_fetcher=fetch)


def test_share_short_link_resolves_to_a_linked_video_through_f2() -> None:
    requested: list[str] = []
    resolver = F2DouyinResolver(_client(requested),
        redirect_follower=lambda _: f"https://www.iesdouyin.com/share/video/{AWEME_ID}/?region=CN")

    video = asyncio.run(resolver.resolve_single_video(_UrlInfo("https://v.douyin.com/hXblWnCsAYc/")))

    assert requested == [AWEME_ID]
    assert (video.source_id, video.title, video.duration_seconds) == (AWEME_ID, "第一行是标题", 62)
    assert video.cover_url == "https://cover.example/origin.jpg"
    assert video.source_url == f"https://www.douyin.com/video/{AWEME_ID}"


def test_missing_cookie_asks_the_user_to_log_in_before_calling_douyin() -> None:
    resolver = F2DouyinResolver(_client(cookie=""))

    with pytest.raises(ExternalVideoResolutionError, match="获取 Cookie"):
        asyncio.run(resolver.resolve_single_video(_UrlInfo(f"https://www.douyin.com/video/{AWEME_ID}")))


def test_download_prefers_browser_playable_h264_within_the_height_cap(tmp_path: Path) -> None:
    fetched: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        assert request.headers["Referer"] == "https://www.douyin.com/"
        return httpx.Response(200, content=b"mp4-bytes", headers={"Content-Length": "9"})

    downloader = F2DouyinDownloader(_client(), max_height=720,
        http_client_factory=lambda **kwargs: httpx.Client(transport=httpx.MockTransport(transport), **kwargs))
    video = asyncio.run(F2DouyinResolver(_client()).resolve_single_video(_UrlInfo(f"https://www.douyin.com/video/{AWEME_ID}")))

    path = downloader.download(video, tmp_path, _Reporter())

    assert fetched == ["https://cdn.example/h264-480.mp4"]
    assert path.read_bytes() == b"mp4-bytes" and path.suffix == ".mp4"
    assert not list(tmp_path.glob("*.part"))


def test_douyin_source_defaults_to_f2_and_accepts_ytdlp(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[4] / "config" / "settings.toml.example"
    path = tmp_path / "settings.toml"
    path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    assert load_settings(path, tmp_path).external_import.douyin.source == "f2"

    path.write_text(path.read_text(encoding="utf-8").replace('source = "f2"', 'source = "yt-dlp"'), encoding="utf-8")
    assert load_settings(path, tmp_path).external_import.douyin.source == "ytdlp"

    path.write_text(path.read_text(encoding="utf-8").replace('source = "yt-dlp"', 'source = "tikhub"'), encoding="utf-8")
    with pytest.raises(ValueError, match="external_import.douyin.source"):
        load_settings(path, tmp_path)
