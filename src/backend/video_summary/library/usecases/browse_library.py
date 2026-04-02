from __future__ import annotations

from backend.video_summary.library.ports import VideoSummaryGenerator, VideoWorkspace
from backend.video_summary.library.views import VideoLibraryView, VideoSummaryView


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
