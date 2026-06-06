from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


@dataclass(frozen=True)
class FakeChaoxingChromiumStatus:
    key: str = "chaoxing-chromium"
    label: str = "Chromium内核"
    local_path: str = "data/playwright-browsers"
    purpose: str = "用于chaoxing登录初始化登录"
    downloaded: bool = False
    status: str = "idle"
    progress: float | None = None
    detail: str | None = None
    error: str | None = None


class ChaoxingDownloadsApiTests(unittest.TestCase):
    def test_gets_chaoxing_chromium_status(self) -> None:
        manager = FakeChaoxingChromiumManager(FakeChaoxingChromiumStatus())
        client = TestClient(create_app(_build_container(manager)))

        response = client.get("/api/linked/chaoxing/chromium")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["key"], "chaoxing-chromium")
        self.assertEqual(payload["label"], "Chromium内核")
        self.assertFalse(payload["downloaded"])

    def test_starts_chaoxing_chromium_download(self) -> None:
        manager = FakeChaoxingChromiumManager(
            FakeChaoxingChromiumStatus(status="running", progress=0.0, detail="正在下载超星 Chromium 浏览器内核")
        )
        client = TestClient(create_app(_build_container(manager)))

        response = client.post("/api/linked/chaoxing/chromium/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(manager.start_download_calls, 1)
        self.assertEqual(response.json()["status"], "running")


class FakeChaoxingChromiumManager:
    def __init__(self, status: FakeChaoxingChromiumStatus) -> None:
        self._status = status
        self.progress_tracker = InMemoryProgressTracker()
        self.start_download_calls = 0

    def get_status(self) -> FakeChaoxingChromiumStatus:
        return self._status

    def start_download(self) -> FakeChaoxingChromiumStatus:
        self.start_download_calls += 1
        return self._status

    def stream_task_id(self) -> str:
        return "chaoxing-chromium-download/chaoxing-chromium"


def _build_container(manager: FakeChaoxingChromiumManager):
    return SimpleNamespace(
        root_dir=None,
        chaoxing_chromium_manager=manager,
    )


if __name__ == "__main__":
    unittest.main()
