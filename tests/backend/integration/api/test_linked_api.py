from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


from backend.api.app import create_app
from backend.bilibili.ytdlp_bilibili import BILIBILI_COOKIE_REQUIRED_MESSAGE
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO


class LinkedApiTests(unittest.TestCase):
    def test_resolve_bilibili_video_returns_linked_video_card(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/linked/bilibili/resolve/video", json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "linked")
        self.assertTrue(payload["is_linked"])
        self.assertEqual(payload["bilibili_bvid"], "BV1xx411c7mD")

    def test_init_bilibili_cookie_returns_configured_status(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/linked/bilibili/cookie/init")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True})
        self.assertTrue(container.bilibili_cookie_initializer.called)

    def test_init_bilibili_cookie_accepts_bilinote_cookie_payload(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post(
            "/api/linked/bilibili/cookie/init",
            json={"cookie": "SESSDATA=session-value; bili_jct=csrf-value"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": True})
        self.assertEqual(container.bilibili_cookie_initializer.cookie, "SESSDATA=session-value; bili_jct=csrf-value")

    def test_update_downloader_cookie_accepts_bilinote_platform_cookie(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post(
            "/api/update_downloader_cookie",
            json={"platform": "bilibili", "cookie": "SESSDATA=session-value; buvid3=fingerprint-value"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        self.assertEqual(container.bilibili_cookie_initializer.cookie, "SESSDATA=session-value; buvid3=fingerprint-value")

    def test_update_downloader_cookie_rejects_sessdata_only_bilibili_cookie(self) -> None:
        container = _build_container(cookie_init_result=ValueError("请粘贴完整 Bilibili 浏览器 Cookie，不能只填写 SESSDATA。"))
        client = TestClient(create_app(container))

        response = client.post(
            "/api/update_downloader_cookie",
            json={"platform": "bilibili", "cookie": "SESSDATA=session-value"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "请粘贴完整 Bilibili 浏览器 Cookie，不能只填写 SESSDATA。")

    def test_get_downloader_cookie_reports_configured_without_leaking_cookie(self) -> None:
        container = _build_container()
        container.bilibili_cookie_config_manager.set("bilibili", "SESSDATA=session-value; bili_jct=csrf-value")
        client = TestClient(create_app(container))

        response = client.get("/api/get_downloader_cookie/bilibili")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"platform": "bilibili", "configured": True})

    def test_create_bilibili_qr_login_session_returns_qrcode_payload(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/linked/bilibili/cookie/qr")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://passport.bilibili.com/qrcode", "qrcode_key": "qr-key"})
        self.assertTrue(container.bilibili_qr_login_service.create_called)

    def test_poll_bilibili_qr_login_returns_configured_status_without_cookie(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/linked/bilibili/cookie/qr/poll", json={"qrcode_key": "qr-key"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "confirmed", "message": "扫码登录成功", "configured": True})
        self.assertEqual(container.bilibili_qr_login_service.polled_key, "qr-key")

    def test_poll_bilibili_qr_login_maps_cookie_save_validation_error_to_conflict(self) -> None:
        container = _build_container()
        container.bilibili_qr_login_service.error = ValueError("请粘贴完整 Bilibili 浏览器 Cookie，不能只填写 SESSDATA。")
        client = TestClient(create_app(container))

        response = client.post("/api/linked/bilibili/cookie/qr/poll", json={"qrcode_key": "qr-key"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "请粘贴完整 Bilibili 浏览器 Cookie，不能只填写 SESSDATA。")

    def test_bilibili_anti_spider_error_returns_cookie_message(self) -> None:
        async def resolve_series(url):
            del url
            raise RuntimeError("ERROR: [BiliBili] x: HTTP Error 412: Precondition Failed")

        client = TestClient(create_app(_build_container(resolve_series=resolve_series)))

        response = client.post("/api/linked/bilibili/resolve/series", json={"url": "https://www.bilibili.com/video/BV1xx411c7mD"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], BILIBILI_COOKIE_REQUIRED_MESSAGE)

    def test_start_linked_video_download_returns_task_id(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/videos/series-1/BV1xx411c7mD/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "started", "task_id": "download/series-1/BV1xx411c7mD"})

    def test_cancel_linked_video_download_marks_task_cancelling(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/videos/series-1/BV1xx411c7mD/download/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "cancelling"})
        snapshot = container.video_download_progress_tracker.get_snapshot("download/series-1/BV1xx411c7mD")
        self.assertEqual(snapshot.status, "cancelling")

    def test_cancel_series_generation_marks_active_video_and_linked_download_tasks(self) -> None:
        container = _build_container(
            active_video_ids=["local-video"],
            videos=[
                LibraryVideoCardDTO(
                    id="local-video",
                    title="本地视频",
                    source_name="local-video.mp4",
                    processed=False,
                    status="pending",
                ),
                LibraryVideoCardDTO(
                    id="BV1xx411c7mD",
                    title="外链视频",
                    source_name="BV1xx411c7mD.mp4",
                    processed=False,
                    status="linked",
                    is_linked=True,
                    bilibili_bvid="BV1xx411c7mD",
                    bilibili_page=1,
                    source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                ),
                LibraryVideoCardDTO(
                    id="ready-video",
                    title="已完成视频",
                    source_name="ready-video.mp4",
                    processed=True,
                    status="ready",
                ),
            ]
        )
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cancelled_video_ids"], ["local-video", "BV1xx411c7mD"])
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series/series-1").status, "cancelling")
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series-1/local-video").status, "cancelling")
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series-1/BV1xx411c7mD").status, "idle")
        self.assertEqual(
            container.video_download_progress_tracker.get_snapshot("download/series-1/BV1xx411c7mD").status,
            "cancelling",
        )
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series-1/ready-video").status, "idle")

    def test_cancel_series_generation_marks_series_cancelled_when_no_backend_series_task_is_active(self) -> None:
        container = _build_container(
            active_video_ids=[],
            videos=[
                LibraryVideoCardDTO(
                    id="BV1xx411c7mD",
                    title="外链视频",
                    source_name="BV1xx411c7mD.mp4",
                    processed=False,
                    status="linked",
                    is_linked=True,
                    bilibili_bvid="BV1xx411c7mD",
                    bilibili_page=1,
                    source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                ),
            ],
        )
        client = TestClient(create_app(container))

        response = client.post("/api/series/series-1/generate/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(container.generation_progress_tracker.get_snapshot("series/series-1").status, "cancelled")


def _build_container(
    videos: list[LibraryVideoCardDTO] | None = None,
    active_video_ids: list[str] | None = None,
    resolve_series=None,
    cookie_init_result=None,
):
    video = LibraryVideoCardDTO(
        id="BV1xx411c7mD",
        title="第一讲",
        source_name="BV1xx411c7mD.mp4",
        processed=False,
        status="linked",
        is_linked=True,
        bilibili_bvid="BV1xx411c7mD",
        bilibili_page=1,
        source_url="https://www.bilibili.com/video/BV1xx411c7mD",
    )
    resolved_videos = videos or [video]
    async def default_resolve_series(url):
        return LibrarySeriesDTO(id="series-1", title="课程", videos=resolved_videos, is_linked=True, source_url=url)

    async def resolve_video(url, target_series_id=None):
        del url, target_series_id
        return video

    generation_progress_tracker = InMemoryProgressTracker()
    bilibili_cookie_initializer = _FakeBilibiliCookieInitializer(cookie_init_result)

    return SimpleNamespace(
        root_dir=None,
        list_video_library=SimpleNamespace(
            run=lambda: SimpleNamespace(
                series=[
                    LibrarySeriesDTO(
                        id="series-1",
                        title="课程",
                        videos=resolved_videos,
                        is_linked=True,
                    )
                ]
            ),
        ),
        resolve_bilibili_series=SimpleNamespace(run=resolve_series or default_resolve_series),
        resolve_bilibili_video=SimpleNamespace(run=resolve_video),
        bilibili_cookie_initializer=bilibili_cookie_initializer,
        bilibili_cookie_config_manager=_FakeBiliNoteCookieConfigManager(),
        bilibili_qr_login_service=_FakeBiliNoteQrLoginService(),
        start_linked_video_download=SimpleNamespace(
            run=lambda series_id, video_id: SimpleNamespace(task_id=f"download/{series_id}/{video_id}"),
        ),
        generate_series_summaries=SimpleNamespace(
            get_active_video_ids=lambda series_id: active_video_ids if active_video_ids is not None else []
        ),
        generation_progress_tracker=generation_progress_tracker,
        video_download_progress_tracker=InMemoryProgressTracker(),
    )


class _FakeBilibiliCookieInitializer:
    def __init__(self, result=None) -> None:
        self.called = False
        self.cookie = None
        self.result = result

    def init(self, cookie: str | None = None) -> bool:
        self.called = True
        self.cookie = cookie
        if isinstance(self.result, Exception):
            raise self.result
        return True


class _FakeBiliNoteCookieConfigManager:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}

    def get(self, platform: str) -> str | None:
        return self.cookies.get(platform)

    def set(self, platform: str, cookie: str) -> None:
        self.cookies[platform] = cookie


class _FakeBiliNoteQrLoginService:
    def __init__(self) -> None:
        self.create_called = False
        self.polled_key = None
        self.error = None

    def create_session(self):
        self.create_called = True
        return SimpleNamespace(url="https://passport.bilibili.com/qrcode", qrcode_key="qr-key")

    def poll(self, qrcode_key: str):
        self.polled_key = qrcode_key
        if self.error is not None:
            raise self.error
        return SimpleNamespace(status="confirmed", message="扫码登录成功", configured=True)


if __name__ == "__main__":
    unittest.main()
