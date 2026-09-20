from __future__ import annotations

import asyncio
from pathlib import Path

from backend.external.ytdlp import (
    BackgroundYtDlpDownloadStarter,
    ExternalVideoResolutionError,
    YtDlpPlatform,
    YtDlpPlatformDownloader,
    YtDlpPlatformResolver,
    _external_platform_error,
)
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.shared.ytdlp import write_cookies_file
from backend.video_summary.library.linked_models import LinkedVideo


YOUTUBE = YtDlpPlatform(
    provider="youtube",
    display_name="YouTube",
    cookie_domain="youtube.com",
    login_url="https://accounts.google.com/ServiceLogin?service=youtube",
    cookie_env="YOUTUBE_COOKIE",
    browser_port=9224,
    login_cookie_names=("SID", "SAPISID", "LOGIN_INFO"),
)


class _UrlInfo:
    def __init__(self, url: str) -> None:
        self.url = url


def test_resolver_maps_youtube_playlist_entries_to_linked_series() -> None:
    resolver = YtDlpPlatformResolver(
        YOUTUBE,
        extractor=lambda _: {
            "id": "PL_test",
            "title": "课程播放列表",
            "thumbnail": "https://example.test/cover.jpg",
            "webpage_url": "https://www.youtube.com/playlist?list=PL_test",
            "entries": [
                {
                    "id": "video_1",
                    "title": "第一讲",
                    "duration": 123.8,
                    "thumbnail": "https://example.test/1.jpg",
                    "webpage_url": "https://www.youtube.com/watch?v=video_1",
                },
                {
                    "id": "video_2",
                    "title": "第二讲",
                    "duration": 45,
                    "webpage_url": "https://www.youtube.com/watch?v=video_2",
                },
            ],
        },
    )

    series = asyncio.run(resolver.resolve_series(_UrlInfo("https://www.youtube.com/playlist?list=PL_test")))

    assert series.series_id == "youtube-PL_test"
    assert [video.video_id for video in series.videos] == ["video_1", "video_2"]
    assert series.videos[0].provider == "youtube"
    assert series.videos[0].duration_seconds == 123


def test_resolver_maps_douyin_single_video() -> None:
    platform = YtDlpPlatform(
        provider="douyin",
        display_name="抖音",
        cookie_domain="douyin.com",
        login_url="https://www.douyin.com/",
        cookie_env="DOUYIN_COOKIE",
        browser_port=9225,
        login_cookie_names=("sessionid", "sessionid_ss"),
    )
    resolver = YtDlpPlatformResolver(
        platform,
        extractor=lambda _: {
            "id": "751234567890",
            "title": "抖音视频",
            "duration": 18,
            "webpage_url": "https://www.douyin.com/video/751234567890",
        },
    )

    video = asyncio.run(resolver.resolve_single_video(_UrlInfo("https://www.douyin.com/video/751234567890")))

    assert video.video_id == "751234567890"
    assert video.provider == "douyin"
    assert video.source_url == "https://www.douyin.com/video/751234567890"


def test_youtube_playlist_entry_without_webpage_url_uses_its_video_id() -> None:
    resolver = YtDlpPlatformResolver(
        YOUTUBE,
        extractor=lambda _: {
            "id": "PL_test",
            "title": "课程播放列表",
            "entries": [{"id": "video_1", "title": "第一讲"}],
        },
    )

    series = asyncio.run(resolver.resolve_series(_UrlInfo("https://www.youtube.com/playlist?list=PL_test")))

    assert series.videos[0].source_url == "https://www.youtube.com/watch?v=video_1"


def test_cookie_file_uses_platform_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = write_cookies_file("SID=session; PREF=value", "youtube.com")

    assert path is not None
    try:
        content = path.read_text(encoding="utf-8")
        assert ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsession" in content
    finally:
        path.unlink(missing_ok=True)


def test_douyin_fresh_cookie_error_is_explained_for_users() -> None:
    platform = YtDlpPlatform(
        provider="douyin",
        display_name="抖音",
        cookie_domain="douyin.com",
        login_url="https://www.douyin.com/",
        cookie_env="DOUYIN_COOKIE",
        browser_port=9225,
        login_cookie_names=("s_v_web_id",),
    )

    def failing_extractor(_: str) -> dict[str, object]:
        raise RuntimeError("ERROR: [Douyin] 123: Fresh cookies (not necessarily logged in) are needed")

    resolver = YtDlpPlatformResolver(platform, extractor=failing_extractor)

    try:
        asyncio.run(resolver.resolve_single_video(_UrlInfo("https://www.douyin.com/video/123")))
    except ExternalVideoResolutionError as error:
        assert error.kind == "cookie_required"
    else:
        raise AssertionError("expected ExternalVideoResolutionError")


def test_downloader_maps_cookie_failure_to_task_error_kind(tmp_path: Path) -> None:
    platform = YtDlpPlatform(
        provider="douyin",
        display_name="抖音",
        cookie_domain="douyin.com",
        login_url="https://www.douyin.com/",
        cookie_env="DOUYIN_COOKIE",
        browser_port=9225,
        login_cookie_names=("s_v_web_id",),
    )
    downloader = YtDlpPlatformDownloader(platform)

    def fail_with_cookie_requirement(*args) -> None:
        del args
        raise RuntimeError("Fresh cookies are needed")

    downloader._run_process = fail_with_cookie_requirement
    reporter = _RecordingReporter()
    video = LinkedVideo(
        source_id="123",
        item_index=1,
        title="视频",
        cover_url="",
        duration_seconds=0,
        source_url="https://www.douyin.com/video/123",
        provider="douyin",
    )

    try:
        downloader.download(video, tmp_path, reporter)
    except ExternalVideoResolutionError as error:
        assert error.kind == "cookie_required"
    else:
        raise AssertionError("expected ExternalVideoResolutionError")
    assert reporter.errors


def test_youtube_verification_failure_tells_user_to_refresh_cookie() -> None:
    error = _external_platform_error(
        RuntimeError("ERROR: [youtube] Sign in to confirm you're not a bot"),
        "YouTube",
    )

    assert error.kind == "cookie_required"
    assert str(error) == "YouTube 需要重新验证登录状态。请重新获取 Cookie 后再试。"


def test_unclassified_platform_failure_never_returns_generic_parse_error() -> None:
    error = _external_platform_error(RuntimeError("yt-dlp exited with an unexpected response"), "YouTube")

    assert error.kind == "failed"
    assert "发生解析错误" not in str(error)
    assert "重新获取 Cookie" in str(error)


def test_background_download_completes_only_after_media_is_saved(tmp_path: Path) -> None:
    media_path = tmp_path / "video.mp4"
    media_path.write_bytes(b"media")
    tracker = InMemoryProgressTracker()
    saved: list[Path] = []

    class Downloader:
        async def download_async(self, _video, _destination, reporter):
            reporter.update("download", 100.0, "文件已下载")
            return media_path

    async def run() -> None:
        starter = BackgroundYtDlpDownloadStarter(
            root_dir=tmp_path,
            downloader=Downloader(),
            progress_tracker=tracker,
            on_downloaded=lambda _series_id, _video_id, path: saved.append(path),
        )
        task_id = starter.start_video(series_id="series-1", video=_linked_video())
        for _ in range(20):
            snapshot = tracker.get_snapshot(task_id)
            if snapshot.status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.01)
        snapshot = tracker.get_snapshot(task_id)
        assert snapshot.status == "completed"
        assert saved == [media_path]

    asyncio.run(run())


def test_background_download_reports_failure_when_media_cannot_be_saved(tmp_path: Path) -> None:
    media_path = tmp_path / "video.mp4"
    media_path.write_bytes(b"media")
    tracker = InMemoryProgressTracker()

    class Downloader:
        async def download_async(self, _video, _destination, reporter):
            reporter.update("download", 100.0, "文件已下载")
            return media_path

    async def run() -> None:
        starter = BackgroundYtDlpDownloadStarter(
            root_dir=tmp_path,
            downloader=Downloader(),
            progress_tracker=tracker,
            on_downloaded=lambda _series_id, _video_id, _path: (_ for _ in ()).throw(OSError("BlobStore unavailable")),
        )
        task_id = starter.start_video(series_id="series-1", video=_linked_video())
        for _ in range(20):
            snapshot = tracker.get_snapshot(task_id)
            if snapshot.status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.01)
        snapshot = tracker.get_snapshot(task_id)
        assert snapshot.status == "failed"
        assert snapshot.error == "下载完成后，媒体保存到工作区失败。请重试。"

    asyncio.run(run())


def _linked_video() -> LinkedVideo:
    return LinkedVideo(
        source_id="video-id",
        item_index=1,
        title="视频",
        cover_url="",
        duration_seconds=0,
        source_url="https://www.youtube.com/watch?v=video-id",
        provider="youtube",
    )


class _RecordingReporter:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def update(self, *args) -> None:
        pass

    def completed(self, *args) -> None:
        pass

    def failed(self, message: str) -> None:
        self.errors.append(message)

    def cancelled(self, *args) -> None:
        pass

    def raise_if_cancelled(self) -> None:
        pass
