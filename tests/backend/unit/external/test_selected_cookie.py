import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.bilibili import ytdlp_bilibili
from backend.external.ytdlp import YOUTUBE_PLATFORM, YtDlpPlatformResolver
from backend.shared.ytdlp import CookieRequiredError


@pytest.mark.parametrize("provider", ["bilibili", "youtube"])
@pytest.mark.parametrize("selected,expected", [
    ("", [False]), ("SID=selected", [True]), (None, [False, True]),
])
def test_selected_cookie_is_one_attempt_while_local_keeps_fallback(monkeypatch, provider, selected, expected):
    calls = []
    class YoutubeDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            authenticated = "cookiefile" in self.options
            calls.append(authenticated)
            if not authenticated:
                raise CookieRequiredError("login required")
            cookie = Path(self.options["cookiefile"]).read_text()
            assert "selected" in cookie if selected else "local" in cookie
            return {"id": "video", "title": "video"}
    monkeypatch.setattr("yt_dlp.YoutubeDL", YoutubeDL)
    monkeypatch.setenv("YOUTUBE_COOKIE", "SID=local")
    monkeypatch.setattr(ytdlp_bilibili, "load_bilibili_headers", lambda _: {"Cookie": "SID=local"})
    def run():
        if provider == "bilibili":
            return ytdlp_bilibili._extract_info("https://www.bilibili.com/video/BV1abc", selected_cookie=selected)
        return asyncio.run(YtDlpPlatformResolver(YOUTUBE_PLATFORM, cookie=selected).resolve_single_video(
            SimpleNamespace(url="https://www.youtube.com/watch?v=video")))
    if selected == "":
        with pytest.raises(RuntimeError):
            run()
    else:
        run()
    assert calls == expected
