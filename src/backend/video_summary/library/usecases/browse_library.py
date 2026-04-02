from __future__ import annotations

from backend.video_summary.library.ports import SummaryCatalog
from backend.video_summary.library.views import VideoLibraryView, VideoSummaryView


class ListVideoLibrary:
    def __init__(self, catalog: SummaryCatalog) -> None:
        self._catalog = catalog

    def run(self) -> VideoLibraryView:
        return VideoLibraryView(
            workspace=self._catalog.get_workspace(),
            series=self._catalog.get_series(),
            videos=self._catalog.list_videos(),
        )


class GetVideoSummary:
    def __init__(self, catalog: SummaryCatalog) -> None:
        self._catalog = catalog

    def run(self, video_id: str) -> VideoSummaryView | None:
        return self._catalog.get_video_summary(video_id)
