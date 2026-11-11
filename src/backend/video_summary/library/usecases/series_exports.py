"""系列级制品批量导出用例。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from backend.video_summary.library.export_filenames import (
    clean_filename_stem,
    unique_filename,
    video_media_stem,
    video_title_stem,
)
from backend.video_summary.library.markdown_exports import (
    render_knowledge_cards_markdown,
    render_mixed_overview_markdown,
)
from backend.video_summary.library.models import (
    KnowledgeCardDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoKnowledgeCardsDTO,
    VideoTranscriptDTO,
)
from backend.video_summary.library.ports import VideoLibraryReader
from backend.video_summary.library.subtitle_exports import render_srt


SERIES_EXPORT_KINDS = {"mixed", "knowledge-cards", "mindmaps", "srt"}
_KIND_LABELS = {
    "mixed": "AI概括混合",
    "knowledge-cards": "知识卡片",
    "mindmaps": "思维导图",
    "srt": "字幕",
}
_ENTRY_LABELS = {
    "mixed": "AI概括混合",
    "knowledge-cards": "知识卡片",
    "mindmaps": "思维导图",
}


@dataclass(frozen=True)
class SeriesExportMissingVideo:
    """某类导出里缺产物、会被跳过的视频。"""

    id: str
    title: str


@dataclass(frozen=True)
class SeriesExportKindAvailability:
    """一类系列导出在选定范围内的可导出情况。"""

    kind: str
    available: int
    total: int
    missing: list[SeriesExportMissingVideo]


@dataclass(frozen=True)
class SeriesExportArchive:
    """系列导出压缩包。"""

    filename: str
    content: bytes


class ExportSeriesArchive:
    """把系列下同类视频制品打包为 zip。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(
        self,
        series_id: str,
        export_kind: str,
        video_ids: list[str] | None = None,
    ) -> SeriesExportArchive:
        if export_kind not in SERIES_EXPORT_KINDS:
            raise ValueError(f"unsupported series export kind '{export_kind}'")

        series = self._find_series(series_id)
        entries = self._build_entries(series, export_kind, set(video_ids or []))
        if not entries:
            raise LookupError(f"no exportable {export_kind} artifacts found for series '{series_id}'")

        series_stem = clean_filename_stem(series.title, fallback=clean_filename_stem(series.id))
        return SeriesExportArchive(
            filename=f"{series_stem}-{_KIND_LABELS[export_kind]}.zip",
            content=_zip_entries(entries),
        )

    def availability(
        self,
        series_id: str,
        video_ids: list[str] | None = None,
    ) -> list[SeriesExportKindAvailability]:
        """统计每类导出在选定范围内有几个视频能导出、缺哪些。

        判断方式与打包时相同，前端据此禁用按钮或提示会跳过的视频。
        """
        series = self._find_series(series_id)
        videos = _select_videos(series, set(video_ids or []))
        result: list[SeriesExportKindAvailability] = []
        for kind in ("mixed", "knowledge-cards", "mindmaps", "srt"):
            missing = [
                SeriesExportMissingVideo(id=video.id, title=video.title)
                for video in videos
                if not self._has_video_export(series.id, video.id, kind)
            ]
            result.append(SeriesExportKindAvailability(
                kind=kind,
                available=len(videos) - len(missing),
                total=len(videos),
                missing=missing,
            ))
        return result

    def _find_series(self, series_id: str) -> LibrarySeriesDTO:
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise LookupError(f"series not found '{series_id}'")
        return series

    def _build_entries(
        self,
        series: LibrarySeriesDTO,
        export_kind: str,
        selected_ids: set[str],
    ) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        used: set[str] = set()
        for index, video in enumerate(series.videos, start=1):
            if selected_ids and video.id not in selected_ids:
                continue
            rendered = self._render_video_export(series.id, video.id, export_kind)
            if rendered is None:
                continue
            entries.append((unique_filename(_entry_filename(index, video, export_kind), used), rendered))
        return entries

    def _has_video_export(self, series_id: str, video_id: str, export_kind: str) -> bool:
        if export_kind == "srt":
            transcript = self._workspace.get_video_transcript(series_id, video_id)
            return transcript is not None and bool(transcript.segments)
        if export_kind == "mixed":
            return (
                self._workspace.get_video_summary(series_id, video_id) is not None
                and self._workspace.get_video_transcript(series_id, video_id) is not None
            )
        if export_kind == "knowledge-cards":
            cards = self._workspace.get_video_knowledge_cards(series_id, video_id)
            return cards is not None and bool(cards.cards)
        return self._workspace.get_video_mindmap(series_id, video_id) is not None

    def _render_video_export(self, series_id: str, video_id: str, export_kind: str) -> str | None:
        if export_kind == "srt":
            transcript = self._workspace.get_video_transcript(series_id, video_id)
            if transcript is None or not transcript.segments:
                return None
            return render_srt(transcript.segments)

        if export_kind == "mixed":
            summary = self._workspace.get_video_summary(series_id, video_id)
            transcript = self._workspace.get_video_transcript(series_id, video_id)
            if summary is None or transcript is None:
                return None
            return render_mixed_overview_markdown(summary.summary, _transcript_payload(transcript))

        if export_kind == "knowledge-cards":
            cards = self._workspace.get_video_knowledge_cards(series_id, video_id)
            if cards is None or not cards.cards:
                return None
            return render_knowledge_cards_markdown(_knowledge_cards_payload(cards))

        mindmap = self._workspace.get_video_mindmap(series_id, video_id)
        if mindmap is None:
            return None
        return _render_mindmap_markdown(mindmap.mindmap).strip() + "\n"


def _select_videos(series: LibrarySeriesDTO, selected_ids: set[str]) -> list[LibraryVideoCardDTO]:
    if not selected_ids:
        return list(series.videos)
    return [video for video in series.videos if video.id in selected_ids]


def _entry_filename(index: int, video: LibraryVideoCardDTO, export_kind: str) -> str:
    """压缩包内文件名。

    字幕不加序号、用原文件名，和视频放在同一目录时播放器能自动加载；
    Markdown 用「序号-标题-类型」，解压后按系列顺序排列。
    """
    if export_kind == "srt":
        return f"{video_media_stem(video.title, video.source_name, video.id, is_linked=video.is_linked)}.srt"
    return f"{index:02d}-{video_title_stem(video.title, video.id)}-{_ENTRY_LABELS[export_kind]}.md"


def _transcript_payload(transcript: VideoTranscriptDTO) -> dict[str, object]:
    return {
        "title": transcript.title,
        "duration_seconds": transcript.duration_seconds,
        "segments": [
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
    }


def _knowledge_cards_payload(cards: VideoKnowledgeCardsDTO) -> dict[str, object]:
    return {
        "title": cards.title,
        "cards": [_knowledge_card_payload(card) for card in cards.cards],
    }


def _knowledge_card_payload(card: KnowledgeCardDTO) -> dict[str, object]:
    return {
        "id": card.id,
        "title": card.title,
        "kind": card.kind,
        "summary": card.summary,
        "details": card.details,
        "tags": list(card.tags),
        "keywords": list(card.keywords),
        "related_card_ids": list(card.related_card_ids),
    }


def _zip_entries(entries: list[tuple[str, str]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for filename, content in entries:
            archive.writestr(filename, content.encode("utf-8"))
    return buffer.getvalue()


def _render_mindmap_markdown(node: dict[str, object], depth: int = 0) -> str:
    indent = "  " * depth
    title = str(node.get("title", ""))
    summary = str(node.get("summary", ""))
    lines = [f"{indent}- **{title}**"]
    if summary:
        lines.append(f"{indent}  {summary}")
    children = node.get("children", []) or []
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                lines.append(_render_mindmap_markdown(child, depth + 1))
    return "\n".join(lines)
