"""库层端口到生成层工作流的桥接适配器。

把 `VideoSummaryGenerator` / `VideoMindmapGenerator`（库层端口）转发到
`ConfiguredVideoSummaryWorkflow` / `ConfiguredMindmapWorkflow`（生成层
工作流），并把 `(series_id, video_id)` 解析为磁盘上的源视频/输出目录。
"""

from __future__ import annotations

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.series_mindmap_workflow import ConfiguredSeriesMindmapWorkflow
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.ports import SeriesMindmapGenerator, VideoLibraryReader, VideoMindmapGenerator, VideoSummaryGenerator


class WorkspaceBackedVideoSummaryGenerator(VideoSummaryGenerator):
    """把库层 `VideoSummaryGenerator` 端口适配为生成层工作流的实现。

    业务场景：在 `library/usecases` 触发的单视频生成流程里，需要按
    `(series_id, video_id)` 拿到磁盘上的源视频与输出目录，再交给
    `ConfiguredVideoSummaryWorkflow` 串起转写 / 总结 / 落盘。

    实现要点：
    - 解析源视频：通过 `_require_video_source` 从 `VideoLibraryReader`
      取出 `source_path` / `output_dir`；缺失则抛 `LookupError`；
    - 进度透传：直接把 `progress_reporter` 转发给工作流，由其内部路由到
      SSE 通道；
    - 错误处理：本类不捕获工作流异常，错误会原样向上抛出给用例层。
    """

    def __init__(self, workspace: VideoLibraryReader, workflow: ConfiguredVideoSummaryWorkflow) -> None:
        """注入工作区读取端口与已配置好的总结工作流。

        Args:
            workspace: 用于按 ID 解析源视频与输出目录的库层端口。
            workflow: 已加载好模型/网关的总结工作流。
        """
        self._workspace = workspace
        self._workflow = workflow

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        """为指定视频触发一次完整的生成工作流。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            progress_reporter: 可选进度 reporter；为 `None` 时由工作流自行
                选择默认值。
            transcript_enhancement_enabled: 是否启用转写增强；为 `None`
                时由工作流按默认配置决定。

        Raises:
            LookupError: 视频不存在时抛出。
        """
        video = _require_video_source(self._workspace, series_id, video_id)
        await self._workflow.run(
            video.source_path,
            video.output_dir,
            progress_reporter=progress_reporter,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
        )


class WorkspaceBackedVideoMindmapGenerator(VideoMindmapGenerator):
    """把库层 `VideoMindmapGenerator` 端口适配为生成层工作流的实现。

    业务场景：在单视频生成流程结束后，需要基于已有的 `summary_data` 重新
    生成思维导图；本适配器负责按 ID 解析视频，再交给思维导图工作流。

    实现要点：
    - 与 `WorkspaceBackedVideoSummaryGenerator` 对称：不感知进度上报 /
      取消；磁盘路径全部由工作区端口解析。
    """

    def __init__(self, workspace: VideoLibraryReader, workflow: ConfiguredMindmapWorkflow) -> None:
        """注入工作区读取端口与已配置好的思维导图工作流。

        Args:
            workspace: 用于按 ID 解析源视频与输出目录的库层端口。
            workflow: 已加载好提示词/网关的思维导图工作流。
        """
        self._workspace = workspace
        self._workflow = workflow

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        summary_data: dict[str, object],
        transcript_text: str = "",
        progress_reporter: ProgressReporter | None = None,
    ) -> None:
        """为指定视频重新生成思维导图。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            summary_data: 总结数据字典，作为思维导图的输入。
            transcript_text: 转写全文文本，可选注入以丰富导图层级细节。
            progress_reporter: 可选进度上报端口；为 `None` 时由工作流自行
                选择默认值。

        Raises:
            LookupError: 视频不存在时抛出。
        """
        video = _require_video_source(self._workspace, series_id, video_id)
        await self._workflow.run(
            video.source_path,
            video.output_dir,
            summary_data,
            transcript_text=transcript_text,
            progress_reporter=progress_reporter,
        )


class WorkspaceBackedSeriesMindmapGenerator(SeriesMindmapGenerator):
    """把库层 `SeriesMindmapGenerator` 端口适配为生成层工作流的实现。

    业务场景：在系列生成流程结束后，需要基于已有的系列目录与所有视频概括
    生成跨视频的思维导图；本适配器负责按 ID 解析系列目录，再交给思维导图工作流。

    实现要点：
    - 与 `WorkspaceBackedVideoMindmapGenerator` 对称：不感知进度上报 / 取消；
      磁盘路径全部由工作区端口解析。
    """

    def __init__(self, workspace: VideoLibraryReader, workflow: ConfiguredSeriesMindmapWorkflow) -> None:
        """注入工作区读取端口与已配置好的系列思维导图工作流。

        Args:
            workspace: 用于按 ID 解析系列目录的库层端口。
            workflow: 已加载好提示词/网关的系列思维导图工作流。
        """
        self._workspace = workspace
        self._workflow = workflow

    async def run(
        self,
        *,
        series_id: str,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
        progress_reporter: ProgressReporter | None = None,
    ) -> None:
        """为指定系列生成跨视频思维导图。

        Args:
            series_id: 系列 ID。
            series_title: 系列标题，用于根节点上下文。
            catalog: 系列目录数据字典（series_catalog.json 的内容）。
            video_summaries: 各视频概括列表，每项应包含 title / one_sentence_summary / chapters 等字段。
            progress_reporter: 可选进度上报端口；为 `None` 时由工作流自行
                选择默认值。
        """
        series_dir = self._workspace.get_series_dir(series_id)
        await self._workflow.run(
            series_dir,
            series_title,
            catalog,
            video_summaries,
            progress_reporter=progress_reporter,
        )


def _require_video_source(workspace: VideoLibraryReader, series_id: str, video_id: str):
    """按 `(series_id, video_id)` 从工作区取源视频信息，不存在则抛 `LookupError`。"""
    video = workspace.get_video_source(series_id, video_id)
    if video is None:
        raise LookupError(f"video not found '{series_id}/{video_id}'")
    return video
