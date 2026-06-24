"""系列级制品批量导出用例。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from backend.video_summary.library.markdown_exports import (
    render_knowledge_cards_markdown,
    render_mixed_overview_markdown,
)
from backend.video_summary.library.models import (
    KnowledgeCardDTO,
    LibrarySeriesDTO,
    VideoKnowledgeCardsDTO,
    VideoTranscriptDTO,
)
from backend.video_summary.library.ports import VideoLibraryReader


SERIES_EXPORT_KINDS = {"mixed", "knowledge-cards", "mindmaps"}


@dataclass(frozen=True)
class SeriesExportArchive:
    """系列导出压缩包。"""

    filename: str
    content: bytes


class ExportSeriesArchive:
    """把系列下同类视频制品打包为 zip。"""

    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, export_kind: str) -> SeriesExportArchive:
        if export_kind not in SERIES_EXPORT_KINDS:
            raise ValueError(f"unsupported series export kind '{export_kind}'")

        series = self._find_series(series_id)
        entries = self._build_entries(series, export_kind)
        if not entries:
            raise LookupError(f"no exportable {export_kind} artifacts found for series '{series_id}'")

        return SeriesExportArchive(
            filename=f"{_safe_filename_part(series.id)}-{export_kind}.zip",
            content=_zip_entries(entries),
        )

    def _find_series(self, series_id: str) -> LibrarySeriesDTO:
        series = next((item for item in self._workspace.list_series() if item.id == series_id), None)
        if series is None:
            raise LookupError(f"series not found '{series_id}'")
        return series

    def _build_entries(self, series: LibrarySeriesDTO, export_kind: str) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        for index, video in enumerate(series.videos, start=1):
            rendered = self._render_video_export(series.id, video.id, export_kind)
            if rendered is None:
                continue
            filename = f"{index:02d}-{_safe_filename_part(video.id)}-{_entry_suffix(export_kind)}.md"
            entries.append((filename, rendered))
        return entries

    def _render_video_export(self, series_id: str, video_id: str, export_kind: str) -> str | None:
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


def _entry_suffix(export_kind: str) -> str:
    if export_kind == "mindmaps":
        return "mindmap"
    return export_kind


def _safe_filename_part(value: str) -> str:
    result = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_"}:
            result.append(char)
        else:
            result.append("-")
    return "".join(result).strip("-") or "export"
