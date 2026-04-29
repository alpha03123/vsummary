from __future__ import annotations

from dataclasses import dataclass

from backend.video_summary.library.constants import PLAYGROUND_SERIES_ID
from backend.video_summary.library.models import (
    BilibiliUrlInfoDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
)
from backend.video_summary.library.linked_models import LinkedSeries
from backend.video_summary.library.parsers import DefaultBilibiliUrlParser
from backend.video_summary.library.ports import (
    BilibiliUrlParser,
    LinkedVideoDownloadStarter,
    LinkedVideoResolver,
    LinkedSeriesResolverWorkspace,
    LinkedSeriesStore,
    WorkspaceIndexInvalidator,
)


@dataclass(frozen=True)
class StartLinkedVideoDownloadResult:
    task_id: str


class ResolveBilibiliSeries:
    def __init__(
        self,
        workspace: LinkedSeriesStore,
        resolver: LinkedVideoResolver,
        invalidator: WorkspaceIndexInvalidator,
        parser: BilibiliUrlParser | None = None,
    ) -> None:
        self._workspace = workspace
        self._resolver = resolver
        self._invalidator = invalidator
        self._parser = parser or DefaultBilibiliUrlParser()

    async def run(self, *, url: str) -> LibrarySeriesDTO:
        url_info = _parse_url(url, self._parser)
        if url_info.url_type == "video":
            video = await self._resolver.resolve_single_video(url_info)
            linked_series = LinkedSeries(
                series_id=f"bilibili-video-{url_info.bvid}",
                title=video.title,
                cover_url=video.cover_url,
                source_url=video.source_url,
                videos=[video],
            )
        else:
            linked_series = await self._resolver.resolve_series(url_info)
        self._workspace.save_linked_series(linked_series)
        self._invalidator.invalidate()
        return _to_series_dto(linked_series)


class ResolveBilibiliVideo:
    def __init__(
        self,
        workspace: LinkedSeriesResolverWorkspace,
        resolver: LinkedVideoResolver,
        invalidator: WorkspaceIndexInvalidator,
        parser: BilibiliUrlParser | None = None,
    ) -> None:
        self._workspace = workspace
        self._resolver = resolver
        self._invalidator = invalidator
        self._parser = parser or DefaultBilibiliUrlParser()

    async def run(self, *, url: str, target_series_id: str | None = None) -> LibraryVideoCardDTO:
        url_info = _parse_url(url, self._parser)
        if url_info.url_type != "video":
            raise ValueError("该端点只接受单视频 URL；合集请使用 /resolve/series。")
        video = await self._resolver.resolve_single_video(url_info)
        resolved_target_series_id = target_series_id or PLAYGROUND_SERIES_ID
        series = next(
            (item for item in self._workspace.list_series() if item.id == resolved_target_series_id),
            None,
        )
        if series is None:
            raise LookupError(f"series not found '{resolved_target_series_id}'")
        existing = self._workspace.get_linked_series(resolved_target_series_id) or LinkedSeries(
            series_id=resolved_target_series_id,
            title=series.title,
            cover_url="",
            source_url="",
            videos=[],
        )
        if not any(item.bvid == video.bvid and item.page == video.page for item in existing.videos):
            self._workspace.save_linked_series(
                LinkedSeries(
                    series_id=existing.series_id,
                    title=existing.title,
                    cover_url=existing.cover_url,
                    source_url=existing.source_url,
                    videos=[*existing.videos, video],
                )
            )
            self._invalidator.invalidate()
        return _to_video_card_dto(video)


class StartLinkedVideoDownload:
    def __init__(self, workspace: LinkedSeriesStore, starter: LinkedVideoDownloadStarter) -> None:
        self._workspace = workspace
        self._starter = starter

    def run(self, *, series_id: str, video_id: str) -> StartLinkedVideoDownloadResult:
        linked_series = self._workspace.get_linked_series(series_id)
        if linked_series is None:
            raise LookupError(f"linked series not found: {series_id}")
        video = next((item for item in linked_series.videos if item.video_id == video_id), None)
        if video is None:
            raise LookupError(f"video not found in linked series: {video_id}")
        return StartLinkedVideoDownloadResult(
            task_id=self._starter.start(
                series_id=series_id,
                video_id=video_id,
                bvid=video.bvid,
                page=video.page,
            )
        )


def _parse_url(url: str, parser: BilibiliUrlParser) -> BilibiliUrlInfoDTO:
    return parser.parse(url)


def _to_series_dto(linked_series: LinkedSeries) -> LibrarySeriesDTO:
    return LibrarySeriesDTO(
        id=linked_series.series_id,
        title=linked_series.title,
        videos=[_to_video_card_dto(video) for video in linked_series.videos],
        is_linked=True,
        source_url=linked_series.source_url,
    )


def _to_video_card_dto(video) -> LibraryVideoCardDTO:
    return LibraryVideoCardDTO(
        id=video.video_id,
        title=video.title,
        source_name=f"{video.video_id}.mp4",
        processed=False,
        status="linked",
        is_linked=True,
        bilibili_bvid=video.bvid,
        bilibili_page=video.page,
        source_url=video.source_url,
    )
