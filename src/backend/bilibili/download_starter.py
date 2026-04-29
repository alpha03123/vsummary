from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.bilibili.bilibili_downloader import BilibiliDownloader
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


def build_video_download_task_id(series_id: str, video_id: str) -> str:
    return f"download/{series_id}/{video_id}"


class BackgroundBilibiliDownloadStarter:
    def __init__(
        self,
        *,
        root_dir: Path,
        downloader: BilibiliDownloader,
        progress_tracker: InMemoryProgressTracker,
        logger: logging.Logger,
    ) -> None:
        self._root_dir = root_dir
        self._downloader = downloader
        self._progress_tracker = progress_tracker
        self._logger = logger

    def task_id_for(self, series_id: str, video_id: str) -> str:
        return build_video_download_task_id(series_id, video_id)

    def start(self, *, series_id: str, video_id: str, bvid: str, page: int) -> str:
        task_id = self.task_id_for(series_id, video_id)
        dest_dir = self._root_dir / "videos" / series_id
        reporter = self._progress_tracker.create_reporter(task_id)

        async def _run() -> None:
            try:
                await self._downloader.download_async(bvid, page, dest_dir, reporter)
            except Exception as exc:
                self._logger.error("Bilibili download failed: %s/%s -> %s", series_id, video_id, exc)

        asyncio.create_task(_run())
        return task_id
