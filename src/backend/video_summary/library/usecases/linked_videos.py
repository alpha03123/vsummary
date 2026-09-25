"""外部链接（B 站）视频解析与下载启动的用例集合。

"链接型"系列在本地只有"元数据 + 解析结果"——尚未真正下载源文件，本模块负责
把用户输入的 B 站 URL 拆解为系列/单视频，并把解析结果回写到 `LinkedSeriesStore`；
下载动作由独立的"下载启动"用例在后续步骤触发。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from backend.video_summary.library.linked_models import LinkedSeries
from backend.video_summary.library.models import (
    BilibiliUrlInfoDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
)
from backend.video_summary.library.parsers import DefaultBilibiliUrlParser
from backend.core.ids import new_ulid
from backend.video_summary.library.ports import (
    BilibiliUrlParser,
    LinkedSeriesResolverWorkspace,
    LinkedSeriesStore,
    LinkedVideoDownloadWorkspace,
    LinkedVideoDownloader,
    LinkedVideoResolver,
    WorkspaceIndexInvalidator,
)


@dataclass(frozen=True)
class ExternalUrlInfo:
    """已完成基础校验的外部视频 URL。"""

    url: str


class ResolveLinkedSeries:
    """按 provider 解析外部系列并保存为链接型系列。"""

    def __init__(self, workspace: LinkedSeriesStore, resolvers: dict[str, object], invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._resolvers = resolvers
        self._invalidator = invalidator

    async def run(self, *, provider: str, url: str) -> LibrarySeriesDTO:
        resolver = _provider_resolver(self._resolvers, provider)
        linked_series = await resolver.resolve_series(ExternalUrlInfo(url=_normalize_external_url(url, provider)))
        self._workspace.save_linked_series(linked_series)
        self._invalidator.invalidate()
        return _to_series_dto(linked_series)


class ResolveLinkedVideo:
    """按 provider 解析单视频并追加到目标链接型系列。"""

    def __init__(self, workspace: LinkedSeriesResolverWorkspace, resolvers: dict[str, object], invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._resolvers = resolvers
        self._invalidator = invalidator

    async def run(
        self,
        *,
        provider: str,
        url: str,
        target_series_id: str | None = None,
    ) -> LibraryVideoCardDTO:
        resolver = _provider_resolver(self._resolvers, provider)
        video = await resolver.resolve_single_video(ExternalUrlInfo(url=_normalize_external_url(url, provider)))
        resolved_target_series_id, series = _resolve_video_target(self._workspace, target_series_id)
        existing = self._workspace.get_linked_series(resolved_target_series_id) or LinkedSeries(
            series_id=resolved_target_series_id,
            title=series.title,
            cover_url="",
            source_url="",
            is_agent_managed=series.is_agent_managed,
            videos=[],
        )
        if not any(item.video_id == video.video_id for item in existing.videos):
            self._workspace.save_linked_series(
                LinkedSeries(
                    series_id=existing.series_id,
                    title=existing.title,
                    cover_url=existing.cover_url,
                    source_url=existing.source_url,
                    is_agent_managed=existing.is_agent_managed,
                    videos=[*existing.videos, video],
                )
            )
            self._invalidator.invalidate()
        return _to_video_card_dto(video)


class CreateAgentLinkedSeries:
    """Create an empty linked series for agent-curated video collections."""

    def __init__(self, workspace: LinkedSeriesResolverWorkspace, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, *, title: str) -> LibrarySeriesDTO:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("title cannot be blank")
        existing = next(
            (item for item in self._workspace.list_series() if item.is_agent_managed and item.title == normalized_title),
            None,
        )
        if existing is not None:
            linked_existing = self._workspace.get_linked_series(existing.id)
            if linked_existing is not None:
                return _to_series_dto(linked_existing)

        linked_series = LinkedSeries(
            series_id=new_ulid(),
            title=normalized_title,
            cover_url="",
            source_url="",
            is_agent_managed=True,
            videos=[],
        )
        self._workspace.save_linked_series(linked_series)
        self._invalidator.invalidate()
        return _to_series_dto(linked_series)


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
    目标系列下；若未指定则默认放入工作区的沙盒系列。
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
        resolved_target_series_id, series = _resolve_video_target(self._workspace, target_series_id)

        existing = self._workspace.get_linked_series(resolved_target_series_id) or LinkedSeries(
            series_id=resolved_target_series_id,
            title=series.title,
            cover_url="",
            source_url="",
            is_agent_managed=series.is_agent_managed,
            videos=[],
        )
        if not any(item.video_id == video.video_id for item in existing.videos):
            self._workspace.save_linked_series(
                LinkedSeries(
                    series_id=existing.series_id,
                    title=existing.title,
                    cover_url=existing.cover_url,
                    source_url=existing.source_url,
                    is_agent_managed=existing.is_agent_managed,
                    videos=[*existing.videos, video],
                )
            )
            self._invalidator.invalidate()
        return _to_video_card_dto(video)


class DownloadLinkedVideo:
    """在持久 Job 的 Worker 租约内下载并提交外链视频。"""

    def __init__(self, workspace: LinkedVideoDownloadWorkspace, downloader: LinkedVideoDownloader) -> None:
        self._workspace = workspace
        self._downloader = downloader

    def run(self, *, series_id: str, video_id: str, reporter) -> None:
        video = self._workspace.get_linked_video_for_download(series_id, video_id)
        if video is None:
            raise LookupError(f"linked video not found: {series_id}/{video_id}")
        reporter.raise_if_cancelled()
        source_path = self._downloader.download(series_id=series_id, video=video, reporter=reporter)
        try:
            reporter.raise_if_cancelled()
            reporter.update("persist", 99.0, "正在保存下载的视频")
            self._workspace.attach_downloaded_file(series_id, video_id, source_path)
        finally:
            source_path.unlink(missing_ok=True)


def _resolve_video_target(
    workspace: LinkedSeriesResolverWorkspace,
    target_series_id: str | None,
) -> tuple[str, LibrarySeriesDTO]:
    series_id = target_series_id or workspace.ensure_playground_series()
    series = next((item for item in workspace.list_series() if item.id == series_id), None)
    if series is None:
        raise LookupError(f"series not found '{series_id}'")
    return series_id, series


def _to_series_dto(linked_series: LinkedSeries) -> LibrarySeriesDTO:
    """把内部 `LinkedSeries` 转换为前端展示用的 `LibrarySeriesDTO`。"""
    return LibrarySeriesDTO(
        id=linked_series.series_id,
        title=linked_series.title,
        videos=[_to_video_card_dto(video) for video in linked_series.videos],
        is_linked=True,
        is_agent_managed=linked_series.is_agent_managed,
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
        source_id=video.source_id,
        item_index=video.item_index,
        source_url=video.source_url,
        provider=video.provider,
    )


_PROVIDER_HOSTS = {
    "bilibili": ("bilibili.com", "b23.tv"),
    "youtube": ("youtube.com", "youtu.be"),
    "douyin": ("douyin.com",),
}


def _provider_resolver(resolvers: dict[str, object], provider: str):
    normalized_provider = provider.strip().lower()
    resolver = resolvers.get(normalized_provider)
    if resolver is None:
        raise ValueError(f"不支持的外部平台：{provider}")
    return resolver


def _normalize_external_url(url: str, provider: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("URL 不能为空。")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        normalized = f"https://{normalized.lstrip('/')}"
    parsed = urlsplit(normalized)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("请输入有效的 HTTP(S) 视频 URL。")
    allowed_hosts = _PROVIDER_HOSTS[provider.strip().lower()]
    if not any(hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts):
        raise ValueError(f"URL 不属于 {provider}。")
    if provider.strip().lower() == "douyin" and parsed.path.rstrip("/") == "/jingxuan":
        modal_id = parse_qs(parsed.query).get("modal_id", [""])[0]
        if modal_id.isdigit():
            return f"https://www.douyin.com/video/{modal_id}"
    return normalized
