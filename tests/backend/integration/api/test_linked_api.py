from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


from backend.api.app import create_app
from backend.video_summary.adapters.progress.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.workspace.models import LibrarySeriesDTO, LibraryVideoCardDTO


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
    async def resolve_series(url):
        return LibrarySeriesDTO(id="series-1", title="课程", videos=resolved_videos, is_linked=True, source_url=url)

    async def resolve_video(url, target_series_id=None):
        del url, target_series_id
        return video

    generation_progress_tracker = InMemoryProgressTracker()

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
        resolve_bilibili_series=SimpleNamespace(run=resolve_series),
        resolve_bilibili_video=SimpleNamespace(run=resolve_video),
        start_linked_video_download=SimpleNamespace(
            run=lambda series_id, video_id: SimpleNamespace(task_id=f"download/{series_id}/{video_id}"),
        ),
        generate_series_summaries=SimpleNamespace(
            get_active_video_ids=lambda series_id: active_video_ids if active_video_ids is not None else []
        ),
        generation_progress_tracker=generation_progress_tracker,
        video_download_progress_tracker=InMemoryProgressTracker(),
    )


if __name__ == "__main__":
    unittest.main()
