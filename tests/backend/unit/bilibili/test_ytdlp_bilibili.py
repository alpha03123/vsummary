from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.bilibili.ytdlp_bilibili import BilibiliDownloader
from backend.bilibili.ytdlp_bilibili import DrissionBilibiliCookieInitializer
from backend.bilibili.ytdlp_bilibili import _extract_info
from backend.bilibili.ytdlp_bilibili import _resolve_default_browser_path


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
    def __init__(self, *, returncode: int = 0, lines: list[str] | None = None) -> None:
        self.stdout = iter(lines or ["[download] 100.0% of 1.00MiB\n"])
        self.returncode = returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


class CapturingReporter(RecordingReporter):
    def __init__(self) -> None:
        super().__init__()
        self.failed_messages: list[str] = []

    def failed(self, message: str) -> None:
        self.failed_messages.append(message)


class CancellingReporter(RecordingReporter):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled_messages: list[str] = []

    def cancelled(self, detail: str | None = None) -> None:
        self.cancelled_messages.append(detail or "")

    def raise_if_cancelled(self) -> None:
        raise RuntimeError("cancel requested")


def test_download_passes_bilibili_cookie_headers_and_prefers_720p_30fps(monkeypatch, tmp_path: Path) -> None:
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
    assert "--format" in cmd
    selected_format = cmd[cmd.index("--format") + 1]
    assert "height<=720" in selected_format
    assert "fps<=30" in selected_format
    assert "User-Agent:Mozilla/5.0" in cmd
    assert "Referer:https://www.bilibili.com/video/BV1xx411c7mD/" in cmd
    assert "--proxy" not in cmd


def test_download_falls_back_to_lower_quality_after_yt_dlp_failure(monkeypatch, tmp_path: Path) -> None:
    captured_formats: list[str] = []

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        selected_format = cmd[cmd.index("--format") + 1]
        captured_formats.append(selected_format)
        if len(captured_formats) == 1:
            return FakeProcess(
                returncode=1,
                lines=["ERROR: [download] Got error: SSL EOF\n"],
            )
        (tmp_path / "BV1xx411c7mD.mp4").write_text("video", encoding="utf-8")
        return FakeProcess()

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)

    result = BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, RecordingReporter())

    assert result == tmp_path / "BV1xx411c7mD.mp4"
    assert len(captured_formats) == 2
    assert "fps<=30" in captured_formats[0]
    assert captured_formats[1] != captured_formats[0]
    assert "height<=720" in captured_formats[1]


def test_download_cancel_does_not_fall_back_to_lower_quality(monkeypatch, tmp_path: Path) -> None:
    popen_calls = 0

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        nonlocal popen_calls
        popen_calls += 1
        return FakeProcess(lines=["[download] 1.0% of 1.00MiB\n"])

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)
    reporter = CancellingReporter()

    with pytest.raises(RuntimeError, match="下载已取消"):
        BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, reporter)

    assert popen_calls == 1
    assert reporter.cancelled_messages == ["下载已取消"]


def test_download_uses_configured_proxy(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        captured["cmd"] = cmd
        (tmp_path / "BV1xx411c7mD.mp4").write_text("video", encoding="utf-8")
        return FakeProcess()

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value")
    monkeypatch.setenv("BILIBILI_YTDLP_PROXY", "direct")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)

    BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, RecordingReporter())

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
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


def test_download_failure_includes_recent_yt_dlp_output(monkeypatch, tmp_path: Path) -> None:
    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        return FakeProcess(
            returncode=1,
            lines=[
                "[BiliBili] Extracting URL\n",
                "ERROR: unable to download video data: HTTP Error 403: Forbidden\n",
            ],
        )

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)
    reporter = CapturingReporter()

    with pytest.raises(RuntimeError) as error:
        BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, reporter)

    message = str(error.value)
    assert "yt-dlp 退出码 1" in message
    assert "HTTP Error 403" in message
    assert reporter.failed_messages == [message]


def test_extract_info_passes_bilibili_cookie_headers(monkeypatch) -> None:
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
    assert "proxy" not in options
    assert options["http_headers"] == {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/video/BV1xx411c7mD/",
    }
    cookiefile = options["cookiefile"]
    assert isinstance(cookiefile, str)
    assert "SESSDATA\tsession-value" in captured["cookies_text"]
    assert not Path(cookiefile).exists()


def test_extract_info_uses_configured_proxy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            captured["options"] = options

        def __enter__(self) -> "FakeYoutubeDL":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def extract_info(self, url: str, download: bool = False) -> dict[str, object]:
            return {"id": "BV1xx411c7mD", "title": "title"}

    monkeypatch.setenv("BILIBILI_YTDLP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)

    _extract_info("https://www.bilibili.com/video/BV1xx411c7mD")

    options = captured["options"]
    assert isinstance(options, dict)
    assert options["proxy"] == "http://127.0.0.1:7890"


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


def test_resolve_default_browser_path_falls_back_to_edge_when_chrome_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("PROGRAMFILES", r"C:\Program Files")
    monkeypatch.setenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    edge_path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

    def exists(path: Path) -> bool:
        return path == edge_path

    assert _resolve_default_browser_path(exists=exists) == str(edge_path)


def test_resolve_default_browser_path_prefers_chrome_before_edge(monkeypatch) -> None:
    monkeypatch.setenv("PROGRAMFILES", r"C:\Program Files")
    monkeypatch.setenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    chrome_path = Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
    edge_path = Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")

    def exists(path: Path) -> bool:
        return path in {chrome_path, edge_path}

    assert _resolve_default_browser_path(exists=exists) == str(chrome_path)
