from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


from backend.api.app import create_app
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

    def test_start_linked_video_download_returns_task_id(self) -> None:
        client = TestClient(create_app(_build_container()))

        response = client.post("/api/videos/series-1/BV1xx411c7mD/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "started", "task_id": "download/series-1/BV1xx411c7mD"})


def _build_container():
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
    async def resolve_series(url):
        return LibrarySeriesDTO(id="series-1", title="课程", videos=[video], is_linked=True, source_url=url)

    async def resolve_video(url, target_series_id=None):
        del url, target_series_id
        return video

    return SimpleNamespace(
        root_dir=None,
        resolve_bilibili_series=SimpleNamespace(run=resolve_series),
        resolve_bilibili_video=SimpleNamespace(run=resolve_video),
        start_linked_video_download=SimpleNamespace(
            run=lambda series_id, video_id: SimpleNamespace(task_id=f"download/{series_id}/{video_id}"),
        ),
        video_download_progress_tracker=InMemoryProgressTracker(),
    )


if __name__ == "__main__":
    unittest.main()
