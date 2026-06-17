"""外部链接（B 站）视频解析与下载启动的用例集合。

"链接型"系列在本地只有"元数据 + 解析结果"——尚未真正下载源文件，本模块负责
把用户输入的 B 站 URL 拆解为系列/单视频，并把解析结果回写到 `LinkedSeriesStore`；
下载动作由独立的"下载启动"用例在后续步骤触发。
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.video_summary.library.constants import PLAYGROUND_SERIES_ID
from backend.video_summary.library.linked_models import LinkedSeries
from backend.video_summary.library.models import (
    BilibiliUrlInfoDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
)
from backend.video_summary.library.parsers import DefaultBilibiliUrlParser
from backend.video_summary.library.ports import (
    BilibiliUrlParser,
    LinkedSeriesResolverWorkspace,
    LinkedSeriesStore,
    LinkedVideoDownloadStarter,
    LinkedVideoResolver,
    WorkspaceIndexInvalidator,
)


@dataclass(frozen=True)
class StartLinkedVideoDownloadResult:
    """下载启动用例的返回值包装。

    Attributes:
        task_id: 用于前端 SSE 订阅进度的下载任务 key。
    """

    task_id: str


class ResolveBilibiliSeries:
    """把 B 站合集/分P URL 解析为一个链接型系列并入库。

    业务场景：用户粘贴一个 B 站合集链接时，本用例一次性拉取所有分P的元数据，
    把它们保存为本地"链接型系列"占位，并使工作区的 RAG 索引失效——这样在
    真正下载并转写之前，链接型系列已经能出现在库视图中。

    副作用：
        - 调用 `LinkedSeriesStore.save_linked_series` 写一条新记录
        - 调用 `WorkspaceIndexInvalidator.invalidate` 让索引下次访问时重建
    """

    def __init__(
        self,
        workspace: LinkedSeriesStore,
        resolver: LinkedVideoResolver,
        invalidator: WorkspaceIndexInvalidator,
        parser: BilibiliUrlParser | None = None,
    ) -> None:
        """注入链接系列存储、解析器、索引失效器与可选的 URL 预处理器。

        Args:
            workspace: 用于保存解析后的链接系列。
            resolver: 真正访问 B 站拉取元数据的解析器。
            invalidator: 用于让工作区索引失效。
            parser: B 站 URL 预处理器（补 scheme、处理 IDN mangled 等），
                若为 `None` 则回退到默认实现。
        """
        self._workspace = workspace
        self._resolver = resolver
        self._invalidator = invalidator
        self._parser = parser or DefaultBilibiliUrlParser()

    async def run(self, *, url: str) -> LibrarySeriesDTO:
        """解析 URL 并把结果回写为链接型系列。

        Args:
            url: 用户输入的 B 站合集/分P URL。

        Returns:
            已落库的链接型系列的展示 DTO（含各分P的视频卡片）。

        Raises:
            任何由 `LinkedVideoResolver` 抛出的异常都会原样上抛（例如非合集
            URL、解析失败等），由调用方转为合适的错误响应。
        """
        linked_series = await self._resolver.resolve_series(self._parser.parse(url))
        self._workspace.save_linked_series(linked_series)
        self._invalidator.invalidate()
        return _to_series_dto(linked_series)


class ResolveBilibiliVideo:
    """把 B 站单视频 URL 解析为单个链接视频，并加入既有或沙盒系列。

    业务场景：用户粘贴单个 B 站视频链接时，本用例解析出元数据并把它挂到指定
    目标系列下；若未指定则默认放入沙盒系列（`PLAYGROUND_SERIES_ID`）。
    同系列下已存在的视频会跳过保存——保证幂等。
    """

    def __init__(
        self,
        workspace: LinkedSeriesResolverWorkspace,
        resolver: LinkedVideoResolver,
        invalidator: WorkspaceIndexInvalidator,
        parser: BilibiliUrlParser | None = None,
    ) -> None:
        """注入读+写链接系列的复合端口、解析器、索引失效器与可选 URL 预处理器。

        Args:
            workspace: 既能读库（用于校验目标系列存在）又能写链接系列的复合端口。
            resolver: 真正访问 B 站拉取元数据的解析器。
            invalidator: 当发生新增时用于让工作区索引失效。
            parser: URL 预处理器；为 `None` 时回退到默认实现。
        """
        self._workspace = workspace
        self._resolver = resolver
        self._invalidator = invalidator
        self._parser = parser or DefaultBilibiliUrlParser()

    async def run(self, *, url: str, target_series_id: str | None = None) -> LibraryVideoCardDTO:
        """解析单视频 URL 并加入目标系列（默认沙盒系列）。

        Args:
            url: 用户输入的 B 站单视频 URL。
            target_series_id: 目标系列 ID；为 `None` 时回退到沙盒系列。

        Returns:
            解析得到的视频卡片 DTO。

        Raises:
            LookupError: 目标系列在本地库中不存在。
        """
        video = await self._resolver.resolve_single_video(self._parser.parse(url))
        resolved_target_series_id = target_series_id or PLAYGROUND_SERIES_ID
        series = next((item for item in self._workspace.list_series() if item.id == resolved_target_series_id), None)
        if series is None:
            raise LookupError(f"series not found '{resolved_target_series_id}'")

        existing = self._workspace.get_linked_series(resolved_target_series_id) or LinkedSeries(
            series_id=resolved_target_series_id,
            title=series.title,
            cover_url="",
            source_url="",
            videos=[],
        )
        if not any(item.video_id == video.video_id for item in existing.videos):
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
    """为链接型系列中的某个视频启动后台下载任务。

    业务场景：用户在链接型系列下点击"下载"按钮时，前端需要拿到一个 task_id
    以便通过 SSE 订阅进度；本用例只做"启动"动作，下载本身在后台异步进行。
    """

    def __init__(self, workspace: LinkedSeriesStore, starter: LinkedVideoDownloadStarter) -> None:
        """注入链接系列存储与下载启动器。

        Args:
            workspace: 用于读取链接系列元数据。
            starter: 真正负责把下载任务投递到后台执行的下游端口。
        """
        self._workspace = workspace
        self._starter = starter

    def run(self, *, series_id: str, video_id: str) -> StartLinkedVideoDownloadResult:
        """为指定视频启动下载并返回 task_id。

        Args:
            series_id: 链接型系列 ID。
            video_id: 系列内某个视频的 ID。

        Returns:
            包含 `task_id` 的结果对象；前端凭此 key 订阅进度。

        Raises:
            LookupError: 系列或视频在链接系列中不存在。
        """
        linked_series = self._workspace.get_linked_series(series_id)
        if linked_series is None:
            raise LookupError(f"linked series not found: {series_id}")
        video = next((item for item in linked_series.videos if item.video_id == video_id), None)
        if video is None:
            raise LookupError(f"video not found in linked series: {video_id}")
        return StartLinkedVideoDownloadResult(task_id=self._starter.start(series_id=series_id, video=video))


def _to_series_dto(linked_series: LinkedSeries) -> LibrarySeriesDTO:
    """把内部 `LinkedSeries` 转换为前端展示用的 `LibrarySeriesDTO`。"""
    return LibrarySeriesDTO(
        id=linked_series.series_id,
        title=linked_series.title,
        videos=[_to_video_card_dto(video) for video in linked_series.videos],
        is_linked=True,
        source_url=linked_series.source_url,
    )


def _to_video_card_dto(video) -> LibraryVideoCardDTO:
    """把内部 `LinkedVideo` 转换为前端展示用的 `LibraryVideoCardDTO`。"""
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
        provider=video.provider,
    )
