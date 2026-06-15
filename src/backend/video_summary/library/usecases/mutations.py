"""库内结构性变更用例（删除系列 / 删除视频）。

结构性变更具有"破坏性 + 级联"两个特点：会清理制品目录、影响 RAG 索引，
因此与只读端口分开封装；并通过"是否有生成任务在跑"的前置校验避免
并发覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.video_summary.library.ports import (
    GenerationActivityChecker,
    VideoMutationStore,
    WorkspaceIndexRefresher,
)


@dataclass(frozen=True)
class DeleteSeriesResult:
    """删除系列用例的返回值包装。

    Attributes:
        series_id: 已删除系列的 ID。
    """

    series_id: str


@dataclass(frozen=True)
class DeleteVideoResult:
    """删除视频用例的返回值包装。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 已删除视频的 ID。
    """

    series_id: str
    video_id: str


class GenerationInProgressError(RuntimeError):
    """目标正在被生成任务占用时抛出。

    删除前必须确保目标没有正在进行的总结/转写任务，否则可能在生成中途
    清理制品导致竞态；由 API 路由捕获并向用户展示"先取消生成"的提示。
    """


class DeleteSeries:
    """删除一个系列及其全部制品。

    业务场景：用户在工作区中清空不再需要的系列；前置校验要求该系列没有
    进行中的生成任务，否则抛 `GenerationInProgressError`。若系列下存在
    已处理的视频，删除后会同步从 RAG 索引中移除，避免检索命中幽灵记录。
    """

    def __init__(
        self,
        workspace: VideoMutationStore,
        index_refresher: WorkspaceIndexRefresher,
        generation_activity_checker: GenerationActivityChecker | None = None,
    ) -> None:
        """注入变更端口、索引刷新器与可选的生成活动查询器。

        Args:
            workspace: 真正执行"删除系列 + 清制品"的下游端口。
            index_refresher: 用于从 RAG 索引中删除整个系列。
            generation_activity_checker: 用于在删除前判定是否有生成任务在跑；
                为 `None` 时跳过该前置校验（适用于测试或离线批处理场景）。
        """
        self._workspace = workspace
        self._index_refresher = index_refresher
        self._generation_activity_checker = generation_activity_checker

    def run(self, series_id: str) -> DeleteSeriesResult:
        """删除指定系列并在需要时清理 RAG 索引。

        Args:
            series_id: 待删除系列 ID。

        Returns:
            包含已删除 series_id 的结果对象。

        Raises:
            GenerationInProgressError: 该系列仍有生成任务在跑。
            LookupError: 系列不存在。
        """
        if (
            self._generation_activity_checker is not None
            and self._generation_activity_checker.is_series_generation_active(series_id)
        ):
            raise GenerationInProgressError(f"系列 '{series_id}' 正在生成，请先取消生成后再删除。")
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        processed_exists = bool(series and any(video.processed for video in series.videos))
        deleted = self._workspace.delete_series(series_id)
        if not deleted:
            raise LookupError(f"series not found '{series_id}'")
        if processed_exists:
            self._index_refresher.delete_series(series_id)
        return DeleteSeriesResult(series_id=series_id)


class DeleteVideoSource:
    """删除单个视频及其全部制品。

    业务场景：用户从系列中移除单条视频；前置校验涵盖"该视频正在生成"与
    "所在系列正在批量生成"两种并发场景，确保不会与正在进行的总结/转写冲突。
    """

    def __init__(
        self,
        workspace: VideoMutationStore,
        index_refresher: WorkspaceIndexRefresher,
        generation_activity_checker: GenerationActivityChecker | None = None,
    ) -> None:
        """注入变更端口、索引刷新器与可选的生成活动查询器。

        Args:
            workspace: 真正执行"删除视频 + 清制品"的下游端口。
            index_refresher: 用于从 RAG 索引中删除单视频。
            generation_activity_checker: 用于在删除前判定是否有生成任务在跑；
                为 `None` 时跳过该前置校验。
        """
        self._workspace = workspace
        self._index_refresher = index_refresher
        self._generation_activity_checker = generation_activity_checker

    def run(self, series_id: str, video_id: str) -> DeleteVideoResult:
        """删除指定视频并在需要时清理 RAG 索引。

        Args:
            series_id: 所属系列 ID。
            video_id: 待删除视频 ID。

        Returns:
            包含已删除 series_id / video_id 的结果对象。

        Raises:
            GenerationInProgressError: 视频或所在系列仍有生成任务在跑。
            LookupError: 视频不存在。
        """
        if (
            self._generation_activity_checker is not None
            and (
                self._generation_activity_checker.is_video_generation_active(series_id, video_id)
                or self._generation_activity_checker.is_series_generation_active(series_id)
            )
        ):
            raise GenerationInProgressError(f"视频 '{series_id}/{video_id}' 正在生成，请先取消生成后再删除。")
        source = self._workspace.get_video_source(series_id, video_id)
        processed = bool(source and source.processed)
        deleted = self._workspace.delete_video(series_id, video_id)
        if not deleted:
            raise LookupError(f"video not found '{series_id}/{video_id}'")
        if processed:
            self._index_refresher.delete_video(series_id, video_id)
        return DeleteVideoResult(series_id=series_id, video_id=video_id)
