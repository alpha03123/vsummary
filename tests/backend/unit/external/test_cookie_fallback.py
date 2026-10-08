from pathlib import Path

import pytest

from backend.bilibili.ytdlp_bilibili import BilibiliDownloader, _extract_info, _extract_view_info
from backend.external.ytdlp import YtDlpPlatformDownloader, YtDlpPlatformResolver
from backend.shared.ytdlp import run_with_cookie_fallback
from backend.video_summary.infrastructure.subtitle_transcripts import _load_bilibili_subtitle
from tests.backend.unit.external.test_ytdlp import YOUTUBE, _RecordingReporter, _linked_video


@pytest.mark.parametrize("platform", ["bilibili", "youtube"])
@pytest.mark.parametrize("failure", [None, "Login required", "HTTP Error 429", "HTTP Error 403", "Connection timed out"])
def test_resolvers_use_cookie_only_for_authentication(platform, failure, monkeypatch):
    monkeypatch.setenv("BILIBILI_COOKIE" if platform == "bilibili" else "YOUTUBE_COOKIE", "SID=secret")
    calls, paths = [], []
    class YoutubeDL:
        def __init__(self, options):
            calls.append(options)
            if "cookiefile" in options:
                path = Path(options["cookiefile"])
                assert "SID\tsecret" in path.read_text(encoding="utf-8")
                paths.append(path)
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def extract_info(self, _url, download):
            if failure and len(calls) == 1:
                raise RuntimeError(failure)
            return {"id": "video", "title": "Video"}
    monkeypatch.setattr("yt_dlp.YoutubeDL", YoutubeDL)
    extract = _extract_info if platform == "bilibili" else YtDlpPlatformResolver(YOUTUBE)._extract_info
    if failure and failure != "Login required":
        with pytest.raises(RuntimeError, match=failure):
            extract("https://www.bilibili.com/video/BV1xx411c7mD")
    else:
        assert extract("https://www.bilibili.com/video/BV1xx411c7mD")["id"] == "video"
    assert "cookiefile" not in calls[0]
    assert "Cookie" not in calls[0]["http_headers"]
    assert len(calls) == (2 if failure == "Login required" else 1)
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize("platform", ["bilibili", "youtube"])
@pytest.mark.parametrize("authenticated_failure", [False, True])
def test_downloader_retries_authentication_once_and_removes_cookie_file(platform, authenticated_failure, monkeypatch, tmp_path):
    monkeypatch.setenv("BILIBILI_COOKIE" if platform == "bilibili" else "YOUTUBE_COOKIE", "SID=secret")
    downloader = BilibiliDownloader() if platform == "bilibili" else YtDlpPlatformDownloader(YOUTUBE)
    calls, cookie_paths = [], []
    def run(command, reporter):
        calls.append(command)
        assert "--ignore-config" in command
        if "--cookies" not in command:
            raise RuntimeError("Sign in to confirm you're not a bot")
        path = Path(command[command.index("--cookies") + 1])
        assert path.is_file()
        cookie_paths.append(path)
        if authenticated_failure:
            raise RuntimeError("Cookies are no longer valid")
        target = command[command.index("--output") + 1].replace("%(ext)s", "mp4")
        Path(target).write_bytes(b"media")
    monkeypatch.setattr(downloader, "_run_process", run)
    def download():
        if platform == "bilibili":
            return downloader.download("BV1xx411c7mD", 1, tmp_path, _RecordingReporter())
        return downloader.download(_linked_video(), tmp_path, _RecordingReporter())
    if authenticated_failure:
        with pytest.raises(RuntimeError): download()
    else:
        assert download().read_bytes() == b"media"
    assert len(calls) == 2
    assert "--cookies" not in calls[0]
    assert all(not path.exists() for path in cookie_paths)


def test_bilibili_quality_downgrade_keeps_authenticated_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=secret")
    downloader = BilibiliDownloader()
    calls = []
    def run(command, reporter):
        calls.append(command)
        if len(calls) == 1:
            raise RuntimeError("Login required")
        if len(calls) == 2:
            raise RuntimeError("Requested format is not available")
        assert "--cookies" in command
        Path(command[command.index("--output") + 1].replace("%(ext)s", "mp4")).write_bytes(b"media")
    monkeypatch.setattr(downloader, "_run_process", run)
    assert downloader.download("BV1xx411c7mD", 1, tmp_path, _RecordingReporter()).is_file()
    assert len(calls) == 3
    assert calls[1][calls[1].index("--cookies") + 1] == calls[2][calls[2].index("--cookies") + 1]
    assert calls[1][calls[1].index("--format") + 1] != calls[2][calls[2].index("--format") + 1]


@pytest.mark.parametrize("requires_login", [False, True])
def test_subtitle_login_warning_triggers_cookie_but_missing_subtitles_does_not(monkeypatch, requires_login):
    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=secret")
    calls = []
    class YoutubeDL:
        def __init__(self, options):
            self.options = options
            calls.append(options)
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def extract_info(self, *_args, **_kwargs):
            if "cookiefile" not in self.options:
                if requires_login:
                    self.options["logger"].warning("Subtitles are only available when logged in")
                return {"subtitles": {}}
            return {"subtitles": {"ai-zh": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nTranscript\n"}]}}
    monkeypatch.setattr("yt_dlp.YoutubeDL", YoutubeDL)
    transcript = _load_bilibili_subtitle("https://www.bilibili.com/video/BV1xx411c7mD")
    assert (transcript is not None) == requires_login
    assert len(calls) == (2 if requires_login else 1)
    assert "cookiefile" not in calls[0]
    if requires_login:
        assert not Path(calls[1]["cookiefile"]).exists()


def test_view_api_uses_cookie_after_explicit_login_code(monkeypatch):
    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=secret")
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"code": -101, "message": "Login required"} if len(calls) == 1 else {"code": 0, "data": {"title": "Video"}}
    def get(_url, **kwargs):
        calls.append(kwargs["headers"])
        return Response()
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.httpx.get", get)
    assert _extract_view_info("BV1xx411c7mD")["title"] == "Video"
    assert "Cookie" not in calls[0]
    assert calls[1]["Cookie"] == "SESSDATA=secret"


def test_cancellation_never_triggers_cookie_retry():
    attempts = []
    def operation(cookie):
        attempts.append(cookie)
        raise InterruptedError("Login required")
    with pytest.raises(InterruptedError):
        run_with_cookie_fallback(operation, "SID=secret")
    assert attempts == [""]
