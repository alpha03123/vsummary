from __future__ import annotations

from backend.video_summary.library.models import VideoMindmapDTO
from backend.video_summary.library.ports import VideoMindmapGenerator, VideoWorkspace


class GenerateVideoMindmapFromLibrary:
    def __init__(self, workspace: VideoWorkspace, generator: VideoMindmapGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    async def run(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        summary = self._workspace.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        try:
            await self._generator.run(
                series_id=series_id,
                video_id=video_id,
                summary_data=summary.summary,
            )
        except LookupError:
            return None
        return self._workspace.get_video_mindmap(series_id, video_id)
