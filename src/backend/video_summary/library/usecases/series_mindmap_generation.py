from __future__ import annotations

from backend.video_summary.library.ports import SeriesMindmapGenerator, VideoLibraryReader


class GenerateSeriesMindmapFromLibrary:
    def __init__(self, workspace: VideoLibraryReader, generator: SeriesMindmapGenerator) -> None:
        self._workspace = workspace
        self._generator = generator

    async def run(self, series_id: str):
        series_list = self._workspace.list_series()
        series = next((s for s in series_list if s.id == series_id), None)
        if series is None or not series.videos:
            return None

        summaries = []
        for video in series.videos:
            summary = self._workspace.get_video_summary(series_id, video.id)
            if summary is not None:
                summaries.append({"title": summary.title, **summary.summary})

        if not summaries:
            return None

        catalog = self._workspace.get_series_catalog(series_id)

        try:
            await self._generator.run(
                series_id=series_id,
                series_title=series.title,
                catalog=catalog,
                video_summaries=summaries,
            )
        except LookupError:
            return None
        return self._workspace.get_series_mindmap(series_id)
