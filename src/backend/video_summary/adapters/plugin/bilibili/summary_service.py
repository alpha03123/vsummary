from __future__ import annotations

import json
from typing import Protocol

from backend.video_summary.workspace.models import BilibiliUrlInfoDTO
from backend.video_summary.workspace.linked_models import LinkedVideo
from backend.video_summary.adapters.plugin.bilibili.workspace import BilibiliPluginWorkspace
from backend.video_summary.adapters.plugin.bilibili.models import (
    BilibiliPluginSummaryResult,
    BilibiliPluginVideoKey,
    BilibiliPluginVideoMeta,
)


class BilibiliSingleVideoResolver(Protocol):
    async def resolve_single_video(self, url_info: BilibiliUrlInfoDTO) -> LinkedVideo:
        ...


class BilibiliTempDownloader(Protocol):
    async def download_async(self, bvid: str, page: int, dest_dir, reporter):
        ...


class VideoSummaryWorkflow(Protocol):
    async def run(
        self,
        source_path,
        output_dir,
        progress_reporter=None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        ...


class PluginProgressTracker(Protocol):
    def create_reporter(self, task_id: str):
        ...


class BilibiliPluginSummaryService:
    def __init__(
        self,
        *,
        workspace: BilibiliPluginWorkspace,
        resolver: BilibiliSingleVideoResolver,
        downloader: BilibiliTempDownloader,
        workflow: VideoSummaryWorkflow,
        progress_tracker: PluginProgressTracker,
    ) -> None:
        self._workspace = workspace
        self._resolver = resolver
        self._downloader = downloader
        self._workflow = workflow
        self._progress_tracker = progress_tracker

    async def run(
        self,
        *,
        url: str,
        transcript_enhancement_enabled: bool | None = None,
    ) -> BilibiliPluginSummaryResult:
        video = await self._resolver.resolve_single_video(BilibiliUrlInfoDTO(url=url))
        key = BilibiliPluginVideoKey(bvid=video.bvid, page=video.page)
        reporter = self._progress_tracker.create_reporter(key.task_id)
        meta = BilibiliPluginVideoMeta(
            bvid=video.bvid,
            page=video.page,
            video_id=video.video_id,
            title=video.title,
            source_url=video.source_url,
            cover_url=video.cover_url,
            duration_seconds=video.duration_seconds,
        )
        self._workspace.save_meta(meta)
        output_dir = self._workspace.output_dir(key)
        try:
            existing = self._workspace.get_summary(key)
            if existing is not None:
                reporter.completed("已读取缓存概况")
                return existing
            reporter.update("download", 5.0, "正在下载 Bilibili 视频到临时目录")
            media_path = await self._downloader.download_async(video.bvid, video.page, self._workspace.temp_dir(key), reporter)
            reporter.update("generate", 20.0, "正在生成视频概况")
            await self._workflow.run(
                media_path,
                output_dir,
                progress_reporter=reporter,
                transcript_enhancement_enabled=transcript_enhancement_enabled,
            )
            result = self._workspace.get_summary(key)
            if result is None:
                raise RuntimeError("概况生成完成但未找到 summary.json。")
            reporter.completed("视频概况已生成")
            return result
        except Exception as error:
            reporter.failed(str(error))
            raise
        finally:
            self._workspace.cleanup_temp_dir(key)

    def get_summary(self, *, bvid: str, page: int = 1) -> BilibiliPluginSummaryResult | None:
        return self._workspace.get_summary(BilibiliPluginVideoKey(bvid=bvid, page=page))


def load_summary_payload(output_dir) -> dict[str, object]:
    summary_path = output_dir / "summary.json"
    if not summary_path.exists():
        raise RuntimeError("summary.json not found")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("summary.json must be an object")
    return payload
