"""视频库的只读查询用例集合。

把"按 series_id/video_id 取一份制品"的查询动作封装为独立用例，对应
`VideoLibraryReader` 端口的每个方法；用例之间互相独立，不做缓存、不做合并，
由 API 路由按需组合。
"""

from __future__ import annotations

from backend.video_summary.library.models import (
    VideoChapterCardsDTO,
    VideoKnowledgeCardsDTO,
    VideoLibraryDTO,
    VideoMindmapDTO,
    VideoSourceDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
    VideoWorkspaceToolsDTO,
)
from backend.video_summary.library.ports import VideoLibraryReader


class ListVideoLibrary:
    """列出工作区下所有系列及其视频卡片。

    业务场景：用户打开工作区主页或刷新库视图时，前端一次性获取工作区元数据
    与系列清单；本用例把"工作区 + 系列"打包为一个 `VideoLibraryDTO` 返回。
    """

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self) -> VideoLibraryDTO:
        """返回工作区基本信息与所有系列的展示数据。"""
        return VideoLibraryDTO(workspace=self._workspace.get_workspace(), series=self._workspace.list_series())


class GetVideoSummary:
    """取单个视频的结构化总结制品。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        """返回指定视频的总结 DTO；若尚未生成则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            总结 DTO，若没有则返回 `None`（区别于"生成失败"）。
        """
        return self._workspace.get_video_summary(series_id, video_id)


class GetVideoSource:
    """取单个视频的源文件与输出目录信息。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        """返回视频的源文件 DTO；视频不存在则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            视频源 DTO，若没有则返回 `None`。
        """
        return self._workspace.get_video_source(series_id, video_id)


class GetVideoTranscript:
    """取单个视频的转写制品。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        """返回视频的转写 DTO；未生成则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            转写 DTO，若没有则返回 `None`。
        """
        return self._workspace.get_video_transcript(series_id, video_id)


class GetVideoMindmap:
    """取单个视频的思维导图制品。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        """返回视频的思维导图 DTO；未生成则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            思维导图 DTO，若没有则返回 `None`。
        """
        return self._workspace.get_video_mindmap(series_id, video_id)


class GetVideoChapterCards:
    """取单个视频的章节卡集合。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        """返回视频的章节卡 DTO；未生成则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            章节卡 DTO，若没有则返回 `None`。
        """
        return self._workspace.get_video_chapter_cards(series_id, video_id)


class GetVideoKnowledgeCards:
    """取单个视频的知识卡集合。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        """返回视频的知识卡 DTO；未生成则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            知识卡 DTO，若没有则返回 `None`。
        """
        return self._workspace.get_video_knowledge_cards(series_id, video_id)


class GetVideoWorkspaceTools:
    """取单个视频的工作区工具栏完整状态。

    业务场景：前端"工作区"标签页一次性展示笔记、思维导图、章节卡等子工具的
    状态卡片；本用例把这些制品的存在与否合并为一个 DTO 返回，避免前端多次
    请求。
    """

    def __init__(self, workspace: VideoLibraryReader) -> None:
        """通过 `VideoLibraryReader` 端口注入具体实现，便于替换。"""
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        """返回工作区工具栏的完整状态 DTO；视频不存在则返回 `None`。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。

        Returns:
            工具栏状态 DTO，若视频不存在则返回 `None`。
        """
        return self._workspace.get_video_workspace_tools(series_id, video_id)


class GetSeriesMindmap:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str) -> VideoMindmapDTO | None:
        return self._workspace.get_series_mindmap(series_id)
