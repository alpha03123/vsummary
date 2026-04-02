from __future__ import annotations

import json
from pathlib import Path

from backend.video_summary.library.views import (
    SeriesView,
    VideoCardView,
    VideoSummaryView,
    WorkspaceView,
)


class SampleSummaryCatalog:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._output_dir = root_dir / "sample" / "output"

    def get_workspace(self) -> WorkspaceView:
        workspace_id = self._root_dir.name
        return WorkspaceView(
            id=workspace_id,
            title=workspace_id.replace("_", " ").replace("-", " ").title(),
        )

    def get_series(self) -> SeriesView:
        series_id = self._output_dir.name
        return SeriesView(
            id=series_id,
            title=series_id.replace("_", " ").replace("-", " ").title(),
        )

    def list_videos(self) -> list[VideoCardView]:
        if not self._output_dir.exists():
            return []

        return [
            VideoCardView(id=directory.name, title=directory.name)
            for directory in sorted(self._output_dir.iterdir())
            if directory.is_dir() and (directory / "summary.json").exists()
        ]

    def get_video_summary(self, video_id: str) -> VideoSummaryView | None:
        summary_path = self._output_dir / video_id / "summary.json"
        if not summary_path.exists():
            return None

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        title = str(summary.get("title", video_id)).strip() or video_id
        return VideoSummaryView(video_id=video_id, title=title, summary=summary)
