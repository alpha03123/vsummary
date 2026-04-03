from __future__ import annotations

import json
from pathlib import Path

from backend.video_summary.library.views import (
    SeriesView,
    VideoCardView,
    VideoMindmapView,
    VideoSourceView,
    VideoSummaryView,
    VideoWorkspaceToolsView,
    WorkspaceToolView,
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
        transcript = _load_transcript(self._workspace_dir / series_id / video_id / "transcript.cleaned.json")
        summary = _attach_chapter_transcript(summary, transcript)
        title = str(summary.get("title", video_id)).strip() or video_id
        return VideoSummaryView(
            series_id=series_id,
            video_id=video_id,
            title=title,
            summary=summary,
        )

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapView | None:
        mindmap_path = self._workspace_dir / series_id / video_id / "mindmap.json"
        if not mindmap_path.exists():
            return None

        summary = self.get_video_summary(series_id, video_id)
        title = summary.title if summary is not None else video_id
        return VideoMindmapView(
            series_id=series_id,
            video_id=video_id,
            title=title,
            mindmap=json.loads(mindmap_path.read_text(encoding="utf-8")),
        )

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsView | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        summary_exists = (video.output_dir / "summary.json").exists()
        mindmap_exists = (video.output_dir / "mindmap.json").exists()
        preview_url = f"/api/videos/{series_id}/{video_id}/preview"
        return VideoWorkspaceToolsView(
            series_id=series_id,
            video_id=video_id,
            overview=WorkspaceToolView(
                id="overview",
                title="AI概况",
                available=True,
                generated=summary_exists,
                status="ready" if summary_exists else "pending",
            ),
            mindmap=WorkspaceToolView(
                id="mindmap",
                title="思维导图",
                available=summary_exists,
                generated=mindmap_exists,
                status="ready" if mindmap_exists else ("available" if summary_exists else "blocked"),
            ),
            preview=WorkspaceToolView(
                id="preview",
                title="视频预览",
                available=True,
                generated=True,
                status="ready",
                preview_url=preview_url,
            ),
            ai_todo="TODO: 后续让 AI 根据当前工具状态触发概况、导图和视频预览联动。",
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


def _load_transcript(transcript_path: Path) -> list[dict[str, object]]:
    if not transcript_path.exists():
        return []

    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = payload.get("segments", [])
    if not isinstance(segments, list):
        return []
    return [segment for segment in segments if isinstance(segment, dict)]


def _attach_chapter_transcript(summary: dict[str, object], transcript_segments: list[dict[str, object]]) -> dict[str, object]:
    chapters = summary.get("chapters", [])
    if not isinstance(chapters, list):
        return summary

    enriched_chapters = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            enriched_chapters.append(chapter)
            continue

        chapter_segments = _slice_transcript_segments(
            transcript_segments,
            _as_seconds(chapter.get("start_seconds")),
            _as_seconds(chapter.get("end_seconds")),
        )
        enriched_chapters.append(
            {
                **chapter,
                "transcript_segments": chapter_segments,
            }
        )

    return {
        **summary,
        "chapters": enriched_chapters,
    }


def _slice_transcript_segments(
    transcript_segments: list[dict[str, object]],
    start_seconds: float | None,
    end_seconds: float | None,
) -> list[dict[str, object]]:
    if start_seconds is None or end_seconds is None:
        return []

    sliced_segments = []
    for segment in transcript_segments:
        segment_start = _as_seconds(segment.get("start_seconds"))
        segment_end = _as_seconds(segment.get("end_seconds"))
        segment_text = segment.get("text")
        if segment_start is None or segment_end is None or not isinstance(segment_text, str) or not segment_text.strip():
            continue
        if segment_end < start_seconds or segment_start > end_seconds:
            continue

        sliced_segments.append(
            {
                "start_seconds": segment_start,
                "end_seconds": segment_end,
                "text": segment_text.strip(),
            }
        )

    return sliced_segments


def _as_seconds(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
