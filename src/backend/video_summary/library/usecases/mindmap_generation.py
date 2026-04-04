from __future__ import annotations

from backend.video_summary.library.ports import VideoMindmapGenerator, VideoWorkspace
from backend.video_summary.library.views import VideoMindmapView


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
