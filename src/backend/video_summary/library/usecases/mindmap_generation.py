"""单视频思维导图生成的用例。

思维导图是总结的可视化分支表达，本模块只负责"读已有总结 → 调生成器落盘 →
回读制品"这一段；不涉及转写或总结本身。
"""

from __future__ import annotations

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.library.models import VideoMindmapDTO
from backend.video_summary.library.ports import VideoLibraryReader, VideoMindmapGenerator


class GenerateVideoMindmapFromLibrary:
    """基于已有视频总结生成思维导图并落盘。

    业务场景：用户已经完成总结后，希望进一步得到可视化的思维导图；本用例
    直接复用总结数据作为生成器输入，避免重复 LLM 调用。
    前置条件：必须先存在 `VideoSummaryDTO`；缺失则短路返回 `None`。
    """

    def __init__(self, workspace: VideoLibraryReader, generator: VideoMindmapGenerator) -> None:
        """注入只读端口与思维导图生成器。

        Args:
            workspace: 用于读取视频总结与回读最终思维导图制品。
            generator: 真正把总结数据转化为思维导图节点/边的下游端口，
                副作用是落盘到视频制品目录。
        """
        self._workspace = workspace
        self._generator = generator

    async def run(
        self,
        series_id: str,
        video_id: str,
        progress_reporter: ProgressReporter | None = None,
    ) -> VideoMindmapDTO | None:
        """为指定视频生成思维导图并返回最终制品 DTO。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            progress_reporter: 可选进度上报端口；为 `None` 时不进行 SSE 上报。

        Returns:
            落盘后的 `VideoMindmapDTO`；总结不存在或生成器抛 `LookupError` 时
            返回 `None`，其余异常由调用方接收。
        """
        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        transcript = self._workspace.get_video_transcript(series_id, video_id)
        transcript_text = "\n".join(s.text for s in transcript.segments) if transcript is not None else ""

        try:
            await self._generator.run(
                series_id=series_id,
                video_id=video_id,
                summary_data=summary.summary,
                transcript_text=transcript_text,
                progress_reporter=progress_reporter,
            )
        except LookupError:
            return None
        return self._workspace.get_video_mindmap(series_id, video_id)
