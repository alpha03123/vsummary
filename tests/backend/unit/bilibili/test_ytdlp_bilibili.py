from __future__ import annotations

import os
import json
from pathlib import Path

import httpx
import pytest

import backend.bilibili.ytdlp_bilibili as ytdlp_module
from backend.bilibili.ytdlp_bilibili import BilibiliDownloader
from backend.bilibili.ytdlp_bilibili import BiliNoteBilibiliCookieInitializer
from backend.bilibili.ytdlp_bilibili import BiliNoteCookieConfigManager
from backend.bilibili.ytdlp_bilibili import BiliNoteQrLoginService
from backend.bilibili.ytdlp_bilibili import BilibiliCookieInitError
from backend.bilibili.ytdlp_bilibili import DrissionBilibiliCookieInitializer
from backend.bilibili.ytdlp_bilibili import _extract_info


@pytest.fixture(autouse=True)
def isolate_bilinote_cookie_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BILINOTE_DOWNLOADER_COOKIE_FILE", str(tmp_path / "isolated-downloader.json"))


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


class CapturingReporter(RecordingReporter):
    def __init__(self) -> None:
        super().__init__()
        self.failed_messages: list[str] = []

    def failed(self, message: str) -> None:
        self.failed_messages.append(message)


class FakeProcess:
    def __init__(self, stdout: list[str] | None = None, returncode: int = 0) -> None:
        self.stdout = iter(stdout or ["[download] 100.0% of 1.00MiB\n"])
        self.returncode = returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


def test_bilinote_cookie_config_manager_persists_platform_cookie(tmp_path: Path) -> None:
    manager = BiliNoteCookieConfigManager(tmp_path / "config" / "downloader.json")

    manager.set("bilibili", "SESSDATA=session-value; bili_jct=csrf-value")

    assert manager.get("bilibili") == "SESSDATA=session-value; bili_jct=csrf-value"
    assert manager.list_all() == {"bilibili": "SESSDATA=session-value; bili_jct=csrf-value"}


def test_download_prefers_bilinote_cookie_config_over_env(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    cookie_config_path = tmp_path / "config" / "downloader.json"
    BiliNoteCookieConfigManager(cookie_config_path).set("bilibili", "SESSDATA=config-session; bili_jct=config-csrf")

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        captured["cmd"] = cmd
        cookies_path = Path(cmd[cmd.index("--cookies") + 1])
        captured["cookies_text"] = cookies_path.read_text(encoding="utf-8")
        (tmp_path / "BV1xx411c7mD.mp4").write_text("video", encoding="utf-8")
        return FakeProcess()

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=env-session")
    monkeypatch.setenv("BILINOTE_DOWNLOADER_COOKIE_FILE", str(cookie_config_path))
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)

    result = BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, RecordingReporter())

    assert result == tmp_path / "BV1xx411c7mD.mp4"
    assert ".bilibili.com\tTRUE\t/\tTRUE\t2147483647\tSESSDATA\tconfig-session" in captured["cookies_text"]
    assert "bili_jct\tconfig-csrf" in captured["cookies_text"]
    assert "env-session" not in captured["cookies_text"]


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


def test_download_ignores_legacy_edge_browser_cookie_source(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        captured["cmd"] = cmd
        (tmp_path / "BV1xx411c7mD.mp4").write_text("video", encoding="utf-8")
        return FakeProcess()

    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)
    monkeypatch.delenv("BILIBILI_SESSDATA", raising=False)
    monkeypatch.setenv("BILIBILI_COOKIE_BROWSER", "edge")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)

    result = BilibiliDownloader().download("BV1xx411c7mD", 1, tmp_path, RecordingReporter())

    assert result == tmp_path / "BV1xx411c7mD.mp4"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert "--cookies-from-browser" not in cmd
    assert "--cookies" not in cmd


def test_download_reports_bilibili_412_as_cookie_required(monkeypatch, tmp_path: Path) -> None:
    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        return FakeProcess(
            stdout=[
                "[BiliBili] BV14PfuBmEN3: Downloading video format 116 for cid 36227057029\n",
                "ERROR: [BiliBili] 14PfuBmEN3: Unable to download JSON metadata: "
                "HTTP Error 412: Precondition Failed\n",
            ],
            returncode=1,
        )

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value; bili_jct=csrf-value")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili._download_bilibili_via_browser", lambda *_args: None)
    reporter = CapturingReporter()

    try:
        BilibiliDownloader().download("BV14PfuBmEN3", 1, tmp_path, reporter)
    except RuntimeError as error:
        assert str(error) == "风控拦截，请配置cookie"
    else:
        raise AssertionError("download should fail")

    assert reporter.failed_messages == ["风控拦截，请配置cookie"]


def test_download_falls_back_to_browser_when_bilibili_412(monkeypatch, tmp_path: Path) -> None:
    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        return FakeProcess(
            stdout=[
                "[BiliBili] BV14PfuBmEN3: Downloading video format 116 for cid 36227057029\n",
                "ERROR: [BiliBili] 14PfuBmEN3: Unable to download JSON metadata: "
                "HTTP Error 412: Precondition Failed\n",
            ],
            returncode=1,
        )

    def fake_browser_download(bvid: str, page: int, dest_dir: Path) -> Path | None:
        assert bvid == "BV14PfuBmEN3"
        assert page == 1
        output = dest_dir / "BV14PfuBmEN3.mp4"
        output.write_text("video", encoding="utf-8")
        return output

    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value; bili_jct=csrf-value")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili._download_bilibili_via_browser", fake_browser_download)
    reporter = CapturingReporter()

    result = BilibiliDownloader().download("BV14PfuBmEN3", 1, tmp_path, reporter)

    assert result == tmp_path / "BV14PfuBmEN3.mp4"
    assert reporter.failed_messages == []


def test_browser_fallback_uses_drission_when_proxy_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "BV14PfuBmEN3.mp4"

    class UnavailableProxyClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "UnavailableProxyClient":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, *args: object, **kwargs: object) -> object:
            raise httpx.ConnectError("proxy unavailable")

    def fake_drission_download(bvid: str, page: int, dest_dir: Path) -> Path | None:
        assert bvid == "BV14PfuBmEN3"
        assert page == 1
        assert dest_dir == tmp_path
        output.write_text("video", encoding="utf-8")
        return output

    monkeypatch.setattr(ytdlp_module.httpx, "Client", UnavailableProxyClient)
    monkeypatch.setattr(ytdlp_module, "_download_bilibili_via_drission", fake_drission_download, raising=False)

    result = ytdlp_module._download_bilibili_via_browser("BV14PfuBmEN3", 1, tmp_path)

    assert result == output


def test_browser_fallback_can_download_through_native_cdp(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "BV14PfuBmEN3.mp4"
    requests: list[str] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object] | None = None) -> None:
            self._payload = payload or {}

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return self._payload

        def iter_bytes(self):
            yield b"video"

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            pass

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            requests.append(url)
            if url.endswith("/json/version"):
                return FakeResponse({"Browser": "Chrome"})
            if "/json/close/" in url:
                return FakeResponse({})
            raise httpx.ConnectError("legacy proxy unavailable")

        def put(self, url: str, **kwargs: object) -> FakeResponse:
            requests.append(url)
            return FakeResponse({"id": "tab-1", "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/page/tab-1"})

        def stream(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            assert method == "GET"
            assert url == "https://upos.example/video.m4s"
            return FakeResponse()

    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict[str, object]] = []

        def __enter__(self) -> "FakeWebSocket":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def close(self) -> None:
            pass

        def send(self, payload: str) -> None:
            message = json.loads(payload)
            self.messages.append(message)

        def recv(self) -> str:
            last_message = self.messages[-1]
            if last_message["method"] != "Runtime.evaluate":
                return json.dumps({"id": last_message["id"], "result": {}})
            expression = last_message["params"]["expression"]
            if "document.readyState" in expression:
                return json.dumps({
                    "id": last_message["id"],
                    "result": {"result": {"value": "https://www.bilibili.com/video/BV14PfuBmEN3|complete"}},
                })
            return json.dumps({
                "id": last_message["id"],
                "result": {
                    "result": {
                        "value": json.dumps({
                            "url": "https://upos.example/video.m4s",
                            "ua": "Chrome UA",
                            "referer": "https://www.bilibili.com/video/BV14PfuBmEN3",
                        }),
                    },
                },
            })

    socket = FakeWebSocket()
    monkeypatch.setenv("BILIBILI_COOKIE", "SESSDATA=session-value; bili_jct=csrf-value")
    monkeypatch.setattr(ytdlp_module.httpx, "Client", FakeClient)
    monkeypatch.setattr(ytdlp_module.websocket, "create_connection", lambda *_args, **_kwargs: socket)

    result = ytdlp_module._download_bilibili_via_cdp("BV14PfuBmEN3", 1, tmp_path)

    assert result == output
    ready_checks = [
        message for message in socket.messages
        if message["method"] == "Runtime.evaluate" and "document.readyState" in message["params"]["expression"]
    ]
    assert ready_checks
    set_cookies = [message for message in socket.messages if message["method"] == "Network.setCookies"]
    assert set_cookies
    assert set_cookies[0]["params"]["cookies"][0] == {
        "name": "SESSDATA",
        "value": "session-value",
        "domain": ".bilibili.com",
        "path": "/",
        "secure": True,
    }
    assert any(url.endswith("/json/close/tab-1") for url in requests)


def test_bilibili_playinfo_script_sends_browser_cookies() -> None:
    script = ytdlp_module._build_bilibili_playinfo_script("BV14PfuBmEN3", 1)

    assert "credentials: 'include'" in script


def test_cdp_playinfo_supports_websocket_client_without_context_manager(monkeypatch) -> None:
    class FakeWebSocketNoContext:
        def __init__(self) -> None:
            self.closed = False
            self.last_message: dict[str, object] | None = None

        def send(self, payload: str) -> None:
            self.last_message = json.loads(payload)

        def recv(self) -> str:
            assert self.last_message is not None
            if self.last_message["method"] != "Runtime.evaluate":
                return json.dumps({"id": self.last_message["id"], "result": {}})
            expression = self.last_message["params"]["expression"]
            if "document.readyState" in expression:
                return json.dumps({
                    "id": self.last_message["id"],
                    "result": {"result": {"value": "https://www.bilibili.com/video/BV14PfuBmEN3|complete"}},
                })
            return json.dumps({
                "id": self.last_message["id"],
                "result": {"result": {"value": json.dumps({"url": "https://upos.example/video.m4s"})}},
            })

        def close(self) -> None:
            self.closed = True

    socket = FakeWebSocketNoContext()
    monkeypatch.setattr(ytdlp_module.websocket, "create_connection", lambda *_args, **_kwargs: socket)

    info = ytdlp_module._fetch_bilibili_cdp_playinfo("ws://example", "BV14PfuBmEN3", 1)

    assert info["url"] == "https://upos.example/video.m4s"
    assert socket.closed is True


def test_native_cdp_starts_temporary_chrome_when_port_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    launches: list[list[str]] = []
    closed_ports: list[int] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        launches.append(cmd)
        return FakeProcess()

    monkeypatch.setattr(ytdlp_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ytdlp_module, "_find_chrome_executable", lambda: "chrome.exe")
    monkeypatch.setattr(ytdlp_module, "_download_bilibili_via_cdp_port", lambda *_args: None)
    monkeypatch.setattr(ytdlp_module, "_close_cdp_browser", lambda port: closed_ports.append(port))

    ytdlp_module._download_bilibili_via_cdp("BV14PfuBmEN3", 1, tmp_path)

    assert launches
    assert any("--remote-debugging-port=9223" in arg for arg in launches[0])
    assert "--remote-allow-origins=*" in launches[0]
    assert closed_ports == [9223]


def test_download_keeps_original_failure_when_legacy_edge_source_is_set(monkeypatch, tmp_path: Path) -> None:
    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        return FakeProcess(
            stdout=[
                "ERROR: [BiliBili] 14PfuBmEN3: Unable to download JSON metadata: HTTP Error 412: Precondition Failed\n",
            ],
            returncode=1,
        )

    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)
    monkeypatch.delenv("BILIBILI_SESSDATA", raising=False)
    monkeypatch.setenv("BILIBILI_COOKIE_BROWSER", "edge")
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili.subprocess.Popen", fake_popen)
    monkeypatch.setattr("backend.bilibili.ytdlp_bilibili._download_bilibili_via_browser", lambda *_args: None)
    reporter = CapturingReporter()

    try:
        BilibiliDownloader().download("BV14PfuBmEN3", 1, tmp_path, reporter)
    except RuntimeError as error:
        assert str(error) == "风控拦截，请配置cookie"
    else:
        raise AssertionError("download should fail")

    assert reporter.failed_messages == ["风控拦截，请配置cookie"]


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


def test_extract_info_ignores_legacy_edge_browser_cookie_source(monkeypatch) -> None:
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
            return {"id": "BV1xx411c7mD", "title": "title"}

    monkeypatch.delenv("BILIBILI_COOKIE", raising=False)
    monkeypatch.delenv("BILIBILI_SESSDATA", raising=False)
    monkeypatch.setenv("BILIBILI_COOKIE_BROWSER", "edge")
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)

    payload = _extract_info("https://www.bilibili.com/video/BV1xx411c7mD")

    assert payload == {"id": "BV1xx411c7mD", "title": "title"}
    options = captured["options"]
    assert isinstance(options, dict)
    assert "cookiesfrombrowser" not in options
    assert "cookiefile" not in options


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


def test_bilinote_bilibili_cookie_initializer_writes_downloader_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BILIBILI_COOKIE", "old-cookie")
    monkeypatch.setenv("BILIBILI_SESSDATA", "old-session")
    monkeypatch.setenv("BILIBILI_COOKIE_BROWSER", "edge")
    cookie_config_path = tmp_path / "config" / "downloader.json"

    initialized = BiliNoteBilibiliCookieInitializer(
        root_dir=tmp_path,
        cookie_config_path=cookie_config_path,
    ).init("SESSDATA=session-value; bili_jct=csrf-value")

    assert initialized is True
    assert BiliNoteCookieConfigManager(cookie_config_path).get("bilibili") == "SESSDATA=session-value; bili_jct=csrf-value"
    assert os.environ["BILINOTE_DOWNLOADER_COOKIE_FILE"] == str(cookie_config_path)
    assert "BILIBILI_COOKIE" not in os.environ
    assert "BILIBILI_SESSDATA" not in os.environ
    assert "BILIBILI_COOKIE_BROWSER" not in os.environ


def test_bilinote_bilibili_cookie_initializer_rejects_sessdata_only_cookie(tmp_path: Path) -> None:
    try:
        BiliNoteBilibiliCookieInitializer(
            root_dir=tmp_path,
            cookie_config_path=tmp_path / "config" / "downloader.json",
        ).init("SESSDATA=session-value")
    except BilibiliCookieInitError as error:
        assert str(error) == "请粘贴完整 Bilibili 浏览器 Cookie，不能只填写 SESSDATA。"
    else:
        raise AssertionError("SESSDATA-only cookie should be rejected")


def test_bilinote_qr_login_service_creates_qrcode_session() -> None:
    client = FakeQrHttpClient(
        generate_payload={"code": 0, "data": {"url": "https://passport.bilibili.com/qrcode", "qrcode_key": "qr-key"}},
    )

    session = BiliNoteQrLoginService(http_client_factory=lambda: client).create_session()

    assert session.url == "https://passport.bilibili.com/qrcode"
    assert session.qrcode_key == "qr-key"
    assert client.generate_called is True


def test_bilinote_qr_login_service_saves_cookie_after_scan(tmp_path: Path) -> None:
    cookie_config_path = tmp_path / "config" / "downloader.json"
    client = FakeQrHttpClient(
        generate_payload={"code": 0, "data": {"url": "https://passport.bilibili.com/qrcode", "qrcode_key": "qr-key"}},
        poll_payload={"code": 0, "data": {"code": 0, "message": "扫码登录成功"}},
        cookies={
            "SESSDATA": "session-value",
            "bili_jct": "csrf-value",
            "DedeUserID": "user-id",
            "buvid3": "fingerprint-value",
        },
    )
    initializer = BiliNoteBilibiliCookieInitializer(root_dir=tmp_path, cookie_config_path=cookie_config_path)
    service = BiliNoteQrLoginService(http_client_factory=lambda: client, cookie_initializer=initializer)
    session = service.create_session()

    result = service.poll(session.qrcode_key)

    assert result.status == "confirmed"
    assert result.configured is True
    assert BiliNoteCookieConfigManager(cookie_config_path).get("bilibili") == (
        "SESSDATA=session-value; bili_jct=csrf-value; DedeUserID=user-id; buvid3=fingerprint-value"
    )
    assert client.closed is True


def test_bilinote_qr_login_service_saves_cookie_from_poll_url(tmp_path: Path) -> None:
    cookie_config_path = tmp_path / "config" / "downloader.json"
    client = FakeQrHttpClient(
        generate_payload={"code": 0, "data": {"url": "https://passport.bilibili.com/qrcode", "qrcode_key": "qr-key"}},
        poll_payload={
            "code": 0,
            "data": {
                "code": 0,
                "message": "扫码登录成功",
                "url": "https://www.bilibili.com/?SESSDATA=session-value&bili_jct=csrf-value&DedeUserID=user-id&buvid3=fingerprint-value",
            },
        },
    )
    initializer = BiliNoteBilibiliCookieInitializer(root_dir=tmp_path, cookie_config_path=cookie_config_path)
    service = BiliNoteQrLoginService(http_client_factory=lambda: client, cookie_initializer=initializer)
    session = service.create_session()

    result = service.poll(session.qrcode_key)

    assert result.status == "confirmed"
    assert BiliNoteCookieConfigManager(cookie_config_path).get("bilibili") == (
        "SESSDATA=session-value; bili_jct=csrf-value; DedeUserID=user-id; buvid3=fingerprint-value"
    )
    assert client.closed is True


def test_bilinote_qr_login_service_supplements_device_cookies_before_saving(tmp_path: Path) -> None:
    cookie_config_path = tmp_path / "config" / "downloader.json"
    client = FakeQrHttpClient(
        generate_payload={"code": 0, "data": {"url": "https://passport.bilibili.com/qrcode", "qrcode_key": "qr-key"}},
        poll_payload={
            "code": 0,
            "data": {
                "code": 0,
                "message": "扫码登录成功",
                "url": "https://www.bilibili.com/?SESSDATA=session-value&bili_jct=csrf-value&DedeUserID=user-id",
            },
        },
        cookies_after_homepage={"buvid3": "fingerprint-value", "b_nut": "device-time"},
        fingerprint_payload={"code": 0, "data": {"b_4": "fingerprint4-value"}},
    )
    initializer = BiliNoteBilibiliCookieInitializer(root_dir=tmp_path, cookie_config_path=cookie_config_path)
    service = BiliNoteQrLoginService(http_client_factory=lambda: client, cookie_initializer=initializer)
    session = service.create_session()

    result = service.poll(session.qrcode_key)

    assert result.status == "confirmed"
    assert BiliNoteCookieConfigManager(cookie_config_path).get("bilibili") == (
        "SESSDATA=session-value; bili_jct=csrf-value; DedeUserID=user-id; buvid3=fingerprint-value; b_nut=device-time; buvid4=fingerprint4-value"
    )
    assert "https://www.bilibili.com/" in client.visited_urls
    assert "https://api.bilibili.com/x/frontend/finger/spi" in client.visited_urls


def test_bilinote_qr_login_service_handles_duplicate_cookie_names(tmp_path: Path) -> None:
    cookie_config_path = tmp_path / "config" / "downloader.json"
    client = FakeQrHttpClient(
        generate_payload={"code": 0, "data": {"url": "https://passport.bilibili.com/qrcode", "qrcode_key": "qr-key"}},
        poll_payload={
            "code": 0,
            "data": {
                "code": 0,
                "message": "扫码登录成功",
                "url": "https://www.bilibili.com/?SESSDATA=session-value&bili_jct=csrf-value&DedeUserID=user-id",
            },
        },
    )
    duplicate_cookies = httpx.Cookies()
    duplicate_cookies.set("buvid3", "first-fingerprint", domain=".bilibili.com")
    duplicate_cookies.set("buvid3", "second-fingerprint", domain="www.bilibili.com")
    client.cookies = duplicate_cookies
    initializer = BiliNoteBilibiliCookieInitializer(root_dir=tmp_path, cookie_config_path=cookie_config_path)
    service = BiliNoteQrLoginService(http_client_factory=lambda: client, cookie_initializer=initializer)
    session = service.create_session()

    result = service.poll(session.qrcode_key)

    cookie = BiliNoteCookieConfigManager(cookie_config_path).get("bilibili") or ""
    assert result.status == "confirmed"
    assert "SESSDATA=session-value" in cookie
    assert cookie.count("buvid3=") == 1


def test_bilinote_qr_login_service_closes_session_when_cookie_save_fails() -> None:
    client = FakeQrHttpClient(
        generate_payload={"code": 0, "data": {"url": "https://passport.bilibili.com/qrcode", "qrcode_key": "qr-key"}},
        poll_payload={"code": 0, "data": {"code": 0, "message": "扫码登录成功"}},
        cookies={"SESSDATA": "session-value"},
    )
    initializer = FailingCookieInitializer()
    service = BiliNoteQrLoginService(http_client_factory=lambda: client, cookie_initializer=initializer)
    session = service.create_session()

    try:
        service.poll(session.qrcode_key)
    except BilibiliCookieInitError as error:
        assert str(error) == "save failed"
    else:
        raise AssertionError("poll should raise when saving cookie fails")

    assert client.closed is True
    assert service._clients == {}


class FakeQrResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, object]:
        return self._payload


class FailingCookieInitializer:
    def init(self, cookie: str | None = None) -> bool:
        del cookie
        raise BilibiliCookieInitError("save failed")


class FakeQrCookies:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self._cookies = cookies or {}

    def items(self) -> list[tuple[str, str]]:
        return list(self._cookies.items())

    def update(self, cookies: dict[str, str]) -> None:
        self._cookies.update(cookies)


class FakeQrHttpClient:
    def __init__(
        self,
        *,
        generate_payload: dict[str, object],
        poll_payload: dict[str, object] | None = None,
        cookies: dict[str, str] | None = None,
        cookies_after_homepage: dict[str, str] | None = None,
        fingerprint_payload: dict[str, object] | None = None,
    ) -> None:
        self.generate_payload = generate_payload
        self.poll_payload = poll_payload or {"code": 0, "data": {"code": 86101, "message": "未扫码"}}
        self.cookies = FakeQrCookies(cookies)
        self.cookies_after_homepage = cookies_after_homepage or {}
        self.fingerprint_payload = fingerprint_payload or {"code": 0, "data": {}}
        self.visited_urls: list[str] = []
        self.generate_called = False
        self.closed = False

    def get(self, url: str, **kwargs: object) -> FakeQrResponse:
        self.visited_urls.append(url)
        if url.endswith("/generate"):
            self.generate_called = True
            return FakeQrResponse(self.generate_payload)
        if url.endswith("/poll"):
            assert kwargs.get("params") == {"qrcode_key": "qr-key"}
            return FakeQrResponse(self.poll_payload)
        if url == "https://www.bilibili.com/":
            self.cookies.update(self.cookies_after_homepage)
            return FakeQrResponse({})
        if url == "https://api.bilibili.com/x/frontend/finger/spi":
            return FakeQrResponse(self.fingerprint_payload)
        raise AssertionError(url)

    def close(self) -> None:
        self.closed = True
