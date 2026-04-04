from __future__ import annotations

from backend.video_summary.library.ports import VideoWorkspace
from backend.video_summary.library.views import (
    VideoChapterCardsView,
    VideoKnowledgeCardsView,
    VideoLibraryView,
    VideoMindmapView,
    VideoSourceView,
    VideoSummaryView,
    VideoWorkspaceToolsView,
)


class ListVideoLibrary:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self) -> VideoLibraryView:
        return VideoLibraryView(
            workspace=self._workspace.get_workspace(),
            series=self._workspace.list_series(),
        )


class GetVideoSummary:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoSummaryView | None:
        return self._workspace.get_video_summary(series_id, video_id)


class GetVideoSource:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoSourceView | None:
        return self._workspace.get_video_source(series_id, video_id)


class GetVideoMindmap:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoMindmapView | None:
        return self._workspace.get_video_mindmap(series_id, video_id)


class GetVideoChapterCards:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoChapterCardsView | None:
        return self._workspace.get_video_chapter_cards(series_id, video_id)


class GetVideoKnowledgeCards:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoKnowledgeCardsView | None:
        return self._workspace.get_video_knowledge_cards(series_id, video_id)


class GetVideoWorkspaceTools:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoWorkspaceToolsView | None:
        return self._workspace.get_video_workspace_tools(series_id, video_id)
