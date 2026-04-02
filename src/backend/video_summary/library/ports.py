from __future__ import annotations

from typing import Protocol

from backend.video_summary.library.views import (
    SeriesView,
    VideoCardView,
    VideoSummaryView,
    WorkspaceView,
)


class SummaryCatalog(Protocol):
    def get_workspace(self) -> WorkspaceView:
        ...

    def get_series(self) -> SeriesView:
        ...

    def list_videos(self) -> list[VideoCardView]:
        ...

    def get_video_summary(self, video_id: str) -> VideoSummaryView | None:
        ...
