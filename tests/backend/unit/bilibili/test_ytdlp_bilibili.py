from __future__ import annotations

import os
from pathlib import Path

from backend.bilibili.ytdlp_bilibili import BilibiliDownloader
from backend.bilibili.ytdlp_bilibili import DrissionBilibiliCookieInitializer
from backend.bilibili.ytdlp_bilibili import _extract_info


class RecordingReporter:
    def __init__(self) -> None:
        self.completed_messages: list[str] = []

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        pass

    def completed(self, detail: str | None = None) -> None:
        self.completed_messages.append(detail or "")

    def failed(self, message: str) -> None:
        raise AssertionError(message)

    def cancelled(self, detail: str | None = None) -> None:
        raise AssertionError(detail or "cancelled")

    def raise_if_cancelled(self) -> None:
        pass


class FakeProcess:
    def __init__(self) -> None:
        self.stdout = iter(["[download] 100.0% of 1.00MiB\n"])
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


def test_download_passes_bilibili_cookie_headers_and_disables_proxy(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        (tmp_path / "BV1xx411c7mD.mp4").write_text("video", encoding="utf-8")
        return FakeProcess()

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value; bili_jct=csrf-value")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)

    result = BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, RecordingReporter())

    assert result == tmp_path / "BV1xx411c7mD.mp4"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert "--cookies" in cmd
    assert "--add-header" in cmd
    assert "User-Agent:Mozilla/5.0" in cmd
    assert "Referer:https://www.bilibili.com/video/BV1xx411c7mD/" in cmd
    assert "--proxy" in cmd
    proxy_index = cmd.index("--proxy")
    assert cmd[proxy_index + 1] == ""


def test_download_uses_sessdata_when_full_cookie_is_absent(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        captured["cmd"] = cmd
        cookies_path = Path(cmd[cmd.index("--cookies") + 1])
        captured["cookies_text"] = cookies_path.read_text(encoding="utf-8")
        (tmp_path / "BV1xx411c7mD.mp4").write_text("video", encoding="utf-8")
        return FakeProcess()

    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)
    monkeypatch.setenv("BILIBILI_SESSDATA", "session-value")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)

    result = BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, RecordingReporter())

    assert result == tmp_path / "BV1xx411c7mD.mp4"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    cookies_path = Path(cmd[cmd.index("--cookies") + 1])
    assert "SESSDATA\tsession-value" in captured["cookies_text"]
    assert not cookies_path.exists()


def test_extract_info_passes_bilibili_cookie_headers_and_disables_proxy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            captured["options"] = options

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = False) -> dict[str, object]:
            captured["url"] = url
            captured["download"] = download
            options = captured["options"]
            assert isinstance(options, dict)
            cookiefile = options["cookiefile"]
            assert isinstance(cookiefile, str)
            captured["cookies_text"] = Path(cookiefile).read_text(encoding="utf-8")
            return {"id": "BV1xx411c7mD", "title": "title"}

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value; bili_jct=csrf-value")
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)

    payload = _extract_info("https://www.bilibili.com/video/BV1xx411c7mD")

    assert payload == {"id": "BV1xx411c7mD", "title": "title"}
    options = captured["options"]
    assert isinstance(options, dict)
    assert options["proxy"] == ""
    assert options["http_headers"] == {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/video/BV1xx411c7mD/",
    }
    cookiefile = options["cookiefile"]
    assert isinstance(cookiefile, str)
    assert "SESSDATA\tsession-value" in captured["cookies_text"]
    assert not Path(cookiefile).exists()


def test_bilibili_cookie_initializer_writes_dotenv_and_process_env(monkeypatch, tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_MODEL=test\nBILIBILI_COOKIE=old-cookie\n", encoding="utf-8")

    class FakePage:
        def __init__(self) -> None:
            self.visited_url = ""
            self.closed = False

        def get(self, url: str) -> None:
            self.visited_url = url

        def cookies(self, *, all_domains: bool = True, all_info: bool = False) -> list[dict[str, str]]:
            return [
                {"domain": ".bilibili.com", "name": "SESSDATA", "value": "session-value"},
                {"domain": ".bilibili.com", "name": "bili_jct", "value": "csrf-value"},
                {"domain": ".example.com", "name": "ignored", "value": "ignored"},
            ]

        def quit(self) -> None:
            self.closed = True

    page = FakePage()
    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)

    initialized = DrissionBilibiliCookieInitializer(
        root_dir=tmp_path,
        page_factory=lambda user_data_dir, browser_port: page,
        timeout_seconds=0.1,
        poll_interval_seconds=0.01,
    ).init()

    assert initialized is True
    assert page.visited_url == "https://passport.bilibili.com/login"
    assert page.closed is True
    assert "OPENAI_MODEL=test" in dotenv_path.read_text(encoding="utf-8")
    assert "BILIBILI_COOKIE=SESSDATA=session-value; bili_jct=csrf-value" in dotenv_path.read_text(encoding="utf-8")
    assert os.environ["BILIBILI_COOKIE"] == "SESSDATA=session-value; bili_jct=csrf-value"
