import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.shared.request_pacing import RequestPacer
from backend.shared.ytdlp import run_with_cookie_fallback, CookieRequiredError
from backend.video_summary.infrastructure.config.settings import load_settings, save_settings


@pytest.fixture
def clock(monkeypatch):
    value = SimpleNamespace(now=10.0)
    monkeypatch.setattr("backend.shared.request_pacing.time.time", lambda: value.now)
    monkeypatch.setattr("backend.shared.request_pacing.time.sleep", lambda seconds: setattr(value, "now", value.now + seconds))
    return value


def test_resolver_and_downloader_instances_share_platform_interval(tmp_path, clock):
    path = tmp_path / "douyin.json"
    resolver = RequestPacer(interval_seconds=1, state_path=path)
    downloader = RequestPacer(interval_seconds=1, state_path=path)
    starts = []
    for pacer in [resolver, downloader, resolver]:
        pacer.wait()
        starts.append(clock.now)
    assert starts == pytest.approx([10, 11, 12])
    other_platform = RequestPacer(interval_seconds=.3, state_path=tmp_path / "bilibili.json")
    other_platform.wait()
    assert clock.now == pytest.approx(12)


def test_cookie_retry_obeys_the_same_interval(tmp_path, clock):
    pacer = RequestPacer(interval_seconds=.3, state_path=tmp_path / "bilibili.json")
    attempts = []
    def request(cookie):
        pacer.wait()
        attempts.append((cookie, clock.now))
        if not cookie:
            raise CookieRequiredError("Login required")
        return "ok"
    assert run_with_cookie_fallback(request, "sessionid=test") == "ok"
    assert [value for _, value in attempts] == pytest.approx([10, 10.3])


def test_cancelled_wait_does_not_consume_a_request_slot(tmp_path, clock):
    path = tmp_path / "douyin.json"
    pacer = RequestPacer(interval_seconds=1, state_path=path)
    pacer.wait()
    def cancelled():
        raise InterruptedError("cancelled")
    with pytest.raises(InterruptedError):
        pacer.wait(cancelled)
    assert json.loads(path.read_text())["started_at"] == 10


@pytest.mark.parametrize("provider,interval", [("bilibili", .3), ("douyin", 1)])
def test_metadata_extraction_applies_pacing_to_cookie_retry(tmp_path, monkeypatch, provider, interval):
    from backend.bilibili.ytdlp_bilibili import _extract_info
    from backend.external.ytdlp import YtDlpPlatform, YtDlpPlatformResolver
    options = []
    class Extractor:
        def __init__(self, config):
            self.config = config
            options.append(config)
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, *args, **kwargs):
            if "cookiefile" not in self.config:
                raise CookieRequiredError("Login required")
            return {"id": "test-video"}
    monkeypatch.setattr("yt_dlp.YoutubeDL", Extractor)
    pacer = SimpleNamespace(interval_seconds=interval, wait=Mock())
    if provider == "bilibili":
        monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=test")
        result = _extract_info("https://www.bilibili.com/video/BV15Hev6yEw1", request_pacer=pacer)
    else:
        monkeypatch.setenv("DOUYIN_COOKIE", "sessionid=test")
        platform = YtDlpPlatform("douyin", "Douyin", "douyin.com", "https://www.douyin.com",
                               "DOUYIN_COOKIE", 9225, ("sessionid",))
        result = YtDlpPlatformResolver(platform, request_pacer=pacer)._extract_info("https://www.douyin.com/video/123")
    assert result["id"] == "test-video"
    assert pacer.wait.call_count == 2
    assert all(config["sleep_interval_requests"] == interval for config in options)


def test_settings_roundtrip_preserves_platform_intervals(tmp_path):
    path = tmp_path / "settings.toml"
    shutil.copyfile(Path(__file__).resolve().parents[4] / "config/settings.toml.example", path)
    settings = load_settings(path, tmp_path)
    assert settings.external_import.bilibili.request_delay_seconds == .3
    assert settings.external_import.douyin.request_delay_seconds == 1
    save_settings(path, settings)
    path.write_text(path.read_text(encoding="utf-8").replace("[external_import.douyin]\nrequest_delay_seconds = 1.0",
                                           "[external_import.douyin]\nrequest_delay_seconds = 2.5"), encoding="utf-8")
    updated = load_settings(path, tmp_path)
    assert updated.external_import.douyin.request_delay_seconds == 2.5
    save_settings(path, updated)
    assert load_settings(path, tmp_path).external_import.douyin.request_delay_seconds == 2.5


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "true"])
def test_invalid_platform_interval_is_rejected(tmp_path, value):
    path = tmp_path / "settings.toml"
    example = (Path(__file__).resolve().parents[4] / "config/settings.toml.example").read_text(encoding="utf-8")
    path.write_text(example.replace("[external_import.douyin]\nrequest_delay_seconds = 1.0",
                                  f"[external_import.douyin]\nrequest_delay_seconds = {value}"), encoding="utf-8")
    with pytest.raises(ValueError, match="external_import.douyin.request_delay_seconds"):
        load_settings(path, tmp_path)
