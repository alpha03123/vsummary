from __future__ import annotations

from backend.video_summary.library.ports import VideoSummaryGenerator, VideoWorkspace
from backend.video_summary.library.ports import VideoMindmapGenerator
from backend.video_summary.library.views import (
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


class GetVideoWorkspaceTools:
    def __init__(self, workspace: VideoWorkspace) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoWorkspaceToolsView | None:
        return self._workspace.get_video_workspace_tools(series_id, video_id)


class GenerateVideoSummaryFromLibrary:
    def __init__(self, workspace: VideoWorkspace, generator: VideoSummaryGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    def run(self, series_id: str, video_id: str) -> VideoSummaryView | None:
        video = self._workspace.get_video_source(series_id, video_id)
        if video is None:
            return None

        self._generator.run(video.source_path, video.output_dir)
        return self._workspace.get_video_summary(series_id, video_id)


class GenerateVideoMindmapFromLibrary:
    def __init__(self, workspace: VideoWorkspace, generator: VideoMindmapGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    def run(self, series_id: str, video_id: str) -> VideoMindmapView | None:
        video = self._workspace.get_video_source(series_id, video_id)
        if video is None:
            return None

        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        self._generator.run(video.source_path, video.output_dir, summary.summary)
        return self._workspace.get_video_mindmap(series_id, video_id)
