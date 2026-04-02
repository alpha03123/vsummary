from __future__ import annotations

import json
from pathlib import Path

from backend.video_summary.library.views import (
    SeriesView,
    VideoCardView,
    VideoSourceView,
    VideoSummaryView,
    WorkspaceView,
)

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class FileSystemVideoWorkspace:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._videos_dir = root_dir / "videos"
        self._workspace_dir = root_dir / "workspace"

    def get_workspace(self) -> WorkspaceView:
        workspace_id = self._root_dir.name
        return WorkspaceView(
            id=workspace_id,
            title=_to_title(workspace_id),
        )

    def list_series(self) -> list[SeriesView]:
        if not self._videos_dir.exists():
            return []

        return [
            SeriesView(
                id=series_dir.name,
                title=_to_title(series_dir.name),
                videos=self._list_videos_for_series(series_dir),
            )
            for series_dir in sorted(self._videos_dir.iterdir())
            if series_dir.is_dir()
        ]

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceView | None:
        series_dir = self._videos_dir / series_id
        if not series_dir.exists() or not series_dir.is_dir():
            return None

        matches = [path for path in sorted(series_dir.iterdir()) if _is_video_file(path) and path.stem == video_id]
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(f"Series '{series_id}' contains duplicate video stem '{video_id}'")

        video_path = matches[0]
        output_dir = self._workspace_dir / series_id / video_id
        return VideoSourceView(
            series_id=series_id,
            video_id=video_id,
            title=video_path.stem,
            source_name=video_path.name,
            source_path=video_path,
            output_dir=output_dir,
            processed=(output_dir / "summary.json").exists(),
        )

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryView | None:
        summary_path = self._workspace_dir / series_id / video_id / "summary.json"
        if not summary_path.exists():
            return None

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        title = str(summary.get("title", video_id)).strip() or video_id
        return VideoSummaryView(
            series_id=series_id,
            video_id=video_id,
            title=title,
            summary=summary,
        )

    def _list_videos_for_series(self, series_dir: Path) -> list[VideoCardView]:
        videos = [path for path in sorted(series_dir.iterdir()) if _is_video_file(path)]
        stems = [path.stem for path in videos]
        duplicate_stems = sorted({stem for stem in stems if stems.count(stem) > 1})
        if duplicate_stems:
            raise ValueError(
                f"Series '{series_dir.name}' contains duplicate video stems: {', '.join(duplicate_stems)}"
            )

        return [
            VideoCardView(
                id=video_path.stem,
                title=video_path.stem,
                source_name=video_path.name,
                processed=(self._workspace_dir / series_dir.name / video_path.stem / "summary.json").exists(),
                status="ready"
                if (self._workspace_dir / series_dir.name / video_path.stem / "summary.json").exists()
                else "pending",
            )
            for video_path in videos
        ]


def _is_video_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES


def _to_title(raw_value: str) -> str:
    return raw_value.replace("_", " ").replace("-", " ").title()
