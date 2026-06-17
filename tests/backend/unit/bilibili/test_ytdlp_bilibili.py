from __future__ import annotations

from pathlib import Path

from backend.bilibili.ytdlp_bilibili import BilibiliDownloader


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
