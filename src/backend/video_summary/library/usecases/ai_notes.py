"""直接生成并保存视频 AI 笔记的用例。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.video_summary.library.models import (
    GeneratedVideoAiNoteDTO,
    VideoAiNoteVisualContextDTO,
    VideoNoteDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
    VideoVisualInputFrameDTO,
)
from backend.video_summary.library.note_images import parse_note_image_markers
from backend.video_summary.library.ports import VideoNotesStore, VideoLibraryReader, WorkspaceIndexRefresher


class AiNoteGenerator(Protocol):
    def run(
        self,
        *,
        transcript: VideoTranscriptDTO,
        summary: VideoSummaryDTO | None,
        visual_context: VideoAiNoteVisualContextDTO,
        template: str,
    ) -> GeneratedVideoAiNoteDTO:
        """根据转写生成 Markdown 笔记。"""


def _split_note_title(content: str, *, fallback: str) -> tuple[str, str]:
    """把模型输出的首行一级标题拆出来作为笔记标题。

    提示词要求正文第一行是 `# 标题`；拆出后从正文中移除，避免与笔记详情页
    自身的标题重复渲染。首行不是一级标题时标题回退到 `fallback`。

    Args:
        content: 模型返回的 Markdown 笔记。
        fallback: 没有可用标题时的兜底标题（通常是视频标题）。

    Returns:
        `(笔记标题, 去掉标题行后的正文)`。
    """
    stripped = content.lstrip("\n")
    first_line, _, rest = stripped.partition("\n")
    heading = first_line.strip()
    if heading.startswith("# "):
        title = heading[2:].strip().strip("#").strip()
        if title:
            return title, rest.lstrip("\n")
    return fallback, content


class VideoAiNoteStore(VideoLibraryReader, VideoNotesStore, Protocol):
    """AI 笔记生成需要的读取与写入能力。"""


class GenerateVideoAiNote:
    """读取现有转写，生成一篇 AI 笔记并立即写入笔记列表。"""

    def __init__(
        self,
        workspace: VideoAiNoteStore,
        generator: AiNoteGenerator,
        index_refresher: WorkspaceIndexRefresher | None = None,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._index_refresher = index_refresher

    def run(self, series_id: str, video_id: str, *, template: str) -> VideoNoteDTO | None:
        source = self._workspace.get_video_source(series_id, video_id)
        if source is None:
            return None
        transcript = self._workspace.get_video_transcript(series_id, video_id)
        if transcript is None:
            raise ValueError("请先生成视频转写，再生成 AI 笔记。")
        summary = self._workspace.get_video_summary(series_id, video_id)
        visual_reader = getattr(self._workspace, "get_video_visual_evidence", None)
        visual_evidence = visual_reader(series_id, video_id) if callable(visual_reader) else None
        visual_context = _build_visual_context(source.output_dir, summary, visual_evidence)
        generated = self._generator.run(
            transcript=transcript,
            summary=summary,
            visual_context=visual_context,
            template=template,
        )
        note_title, note_content = _split_note_title(generated.content, fallback=transcript.title)
        note_content = _constrain_ai_note_image_markers(
            note_content,
            summary=summary,
            duration_seconds=transcript.duration_seconds,
            enabled=generated.note_visual_mode == "screenshots",
            max_images=generated.note_max_images,
            min_gap_seconds=generated.note_image_min_gap_seconds,
        )
        note = self._workspace.create_video_note(
            series_id,
            video_id,
            title=note_title,
            content=note_content,
            source="agent",
        )
        if note is not None and self._index_refresher is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return note


def _build_visual_context(output_dir: Path, summary: VideoSummaryDTO | None, visual_evidence) -> VideoAiNoteVisualContextDTO:
    frames: list[VideoVisualInputFrameDTO] = []
    if summary is not None:
        chapters = summary.summary.get("chapters")
        if isinstance(chapters, list):
            for chapter in chapters:
                if not isinstance(chapter, dict):
                    continue
                filename = chapter.get("image_filename")
                timestamp = chapter.get("image_timestamp_seconds")
                chapter_id = chapter.get("id")
                if (
                    isinstance(filename, str)
                    and filename
                    and Path(filename).name == filename
                    and isinstance(timestamp, (int, float))
                    and not isinstance(timestamp, bool)
                    and isinstance(chapter_id, str)
                    and chapter_id.strip()
                ):
                    image_path = output_dir / "screenshots" / filename
                    if image_path.is_file():
                        frames.append(
                            VideoVisualInputFrameDTO(
                                chapter_id=chapter_id,
                                timestamp_seconds=float(timestamp),
                                image_filename=filename,
                                image_path=image_path,
                            )
                        )
    evidence_text = "\n".join(frame.text for frame in visual_evidence.frames) if visual_evidence is not None else ""
    return VideoAiNoteVisualContextDTO(frames=frames, evidence_text=evidence_text)


def _constrain_ai_note_image_markers(
    content: str,
    *,
    summary: VideoSummaryDTO | None,
    duration_seconds: float,
    enabled: bool,
    max_images: int,
    min_gap_seconds: float,
) -> str:
    """删除 AI 不允许的标记，手动笔记不走此函数。"""
    markers = parse_note_image_markers(content)
    if not enabled:
        return _filter_markers(content, set())
    accepted: set[tuple[int, int]] = set()
    for marker in markers:
        if len(accepted) >= max_images or marker.seconds > duration_seconds:
            continue
        chapter = _find_chapter(summary, marker.seconds)
        if chapter is None:
            if summary is None:
                accepted.add((marker.start, marker.end))
            continue
        start, end, overview_timestamps = chapter
        short_chapter = end - start < min_gap_seconds * 2
        if any(
            marker.seconds == timestamp if short_chapter else abs(marker.seconds - timestamp) < min_gap_seconds
            for timestamp in overview_timestamps
        ):
            continue
        accepted.add((marker.start, marker.end))
    return _filter_markers(content, accepted)


def _filter_markers(content: str, accepted: set[tuple[int, int]]) -> str:
    """仅保留指定位置的合法标记；不合法标记本来就不会被解析或删除。"""
    markers = parse_note_image_markers(content)
    if not markers:
        return content
    parts: list[str] = []
    previous = 0
    for marker in markers:
        parts.append(content[previous:marker.start])
        if (marker.start, marker.end) in accepted:
            parts.append(marker.raw)
        previous = marker.end
    parts.append(content[previous:])
    return "".join(parts)


def _overview_timestamps_by_chapter(summary: VideoSummaryDTO | None) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    if summary is None:
        return result
    chapters = summary.summary.get("chapters")
    if not isinstance(chapters, list):
        return result
    for chapter in chapters:
        if isinstance(chapter, dict) and isinstance(chapter.get("id"), str) and isinstance(chapter.get("image_timestamp_seconds"), (int, float)):
            result.setdefault(chapter["id"], []).append(float(chapter["image_timestamp_seconds"]))
    return result


def _find_chapter(summary: VideoSummaryDTO | None, seconds: float):
    if summary is None:
        return None
    chapters = summary.summary.get("chapters")
    if not isinstance(chapters, list):
        return None
    timestamps_by_chapter = _overview_timestamps_by_chapter(summary)
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        start = chapter.get("start_seconds")
        end = chapter.get("end_seconds")
        chapter_id = chapter.get("id")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and isinstance(chapter_id, str) and start <= seconds <= end:
            return float(start), float(end), timestamps_by_chapter.get(chapter_id, [])
    return None
