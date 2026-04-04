from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.video_summary.library.views import (
    ChapterCardView,
    KnowledgeCardView,
    KnowledgeCardSourceRefView,
    SeriesView,
    VideoCardView,
    VideoChapterCardsView,
    VideoKnowledgeCardsView,
    VideoMindmapView,
    VideoNoteView,
    VideoNotesView,
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
        mindmap_path = self._get_video_output_dir(series_id, video_id) / "mindmap.json"
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

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsView | None:
        summary = self.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        return VideoChapterCardsView(
            series_id=series_id,
            video_id=video_id,
            title=summary.title,
            cards=_build_chapter_cards(summary.summary),
        )

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsView | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        knowledge_cards_path = self._get_video_output_dir(series_id, video_id) / "knowledge_cards.json"
        if not knowledge_cards_path.exists():
            return None

        payload = json.loads(knowledge_cards_path.read_text(encoding="utf-8"))
        cards = payload.get("cards", [])
        if not isinstance(cards, list):
            raise ValueError("knowledge_cards.json 格式错误：cards 必须是数组。")

        return VideoKnowledgeCardsView(
            series_id=series_id,
            video_id=video_id,
            title=str(payload.get("title", video.title)).strip() or video.title,
            cards=[_to_knowledge_card_view(card) for card in cards],
        )

    def save_video_knowledge_cards(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        cards: list[KnowledgeCardView],
    ) -> None:
        cards_payload = {
            "title": title,
            "cards": [_serialize_knowledge_card(card) for card in cards],
        }
        output_dir = self._get_video_output_dir(series_id, video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "knowledge_cards.json").write_text(
            json.dumps(cards_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesView | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        notes_payload = self._read_notes_payload(series_id, video_id)
        return VideoNotesView(
            series_id=series_id,
            video_id=video_id,
            title=video.title,
            notes=[
                _to_note_view(note)
                for note in notes_payload["notes"]
            ],
        )

    def create_video_note(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        content: str,
        source: str,
    ) -> VideoNoteView | None:
        if self.get_video_source(series_id, video_id) is None:
            return None

        next_title = _require_note_text(title, "title")
        next_content = _require_note_text(content, "content")
        next_source = _require_note_source(source)
        now = _now_iso()
        note_record = {
            "id": f"note-{uuid4().hex}",
            "title": next_title,
            "content": next_content,
            "source": next_source,
            "created_at": now,
            "updated_at": now,
        }
        notes_payload = self._read_notes_payload(series_id, video_id)
        notes_payload["notes"].append(note_record)
        self._write_notes_payload(series_id, video_id, notes_payload)
        return _to_note_view(note_record)

    def update_video_note(
        self,
        series_id: str,
        video_id: str,
        note_id: str,
        *,
        title: str,
        content: str,
    ) -> VideoNoteView | None:
        if self.get_video_source(series_id, video_id) is None:
            return None

        next_title = _require_note_text(title, "title")
        next_content = _require_note_text(content, "content")
        notes_payload = self._read_notes_payload(series_id, video_id)
        for note in notes_payload["notes"]:
            if note["id"] != note_id:
                continue
            note["title"] = next_title
            note["content"] = next_content
            note["updated_at"] = _now_iso()
            self._write_notes_payload(series_id, video_id, notes_payload)
            return _to_note_view(note)
        return None

    def delete_video_note(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        if self.get_video_source(series_id, video_id) is None:
            return None

        notes_payload = self._read_notes_payload(series_id, video_id)
        remaining_notes = [note for note in notes_payload["notes"] if note["id"] != note_id]
        if len(remaining_notes) == len(notes_payload["notes"]):
            return False

        self._write_notes_payload(series_id, video_id, {"notes": remaining_notes})
        return True

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsView | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        summary_exists = (video.output_dir / "summary.json").exists()
        knowledge_cards_exists = (video.output_dir / "knowledge_cards.json").exists()
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
            knowledge_cards=WorkspaceToolView(
                id="knowledge-cards",
                title="知识卡片",
                available=summary_exists,
                generated=knowledge_cards_exists,
                status="ready" if knowledge_cards_exists else ("available" if summary_exists else "blocked"),
            ),
            mindmap=WorkspaceToolView(
                id="mindmap",
                title="思维导图",
                available=summary_exists,
                generated=mindmap_exists,
                status="ready" if mindmap_exists else ("available" if summary_exists else "blocked"),
            ),
            notes=WorkspaceToolView(
                id="notes",
                title="笔记",
                available=True,
                generated=True,
                status="ready",
            ),
            preview=WorkspaceToolView(
                id="preview",
                title="视频预览",
                available=True,
                generated=True,
                status="ready",
                preview_url=preview_url,
            ),
            ai_todo="当前已支持 AI 切换概况、知识卡片、笔记和视频预览，并可定位时间点或整理笔记。",
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

    def _get_video_output_dir(self, series_id: str, video_id: str) -> Path:
        return self._workspace_dir / series_id / video_id

    def _read_notes_payload(self, series_id: str, video_id: str) -> dict[str, list[dict[str, str]]]:
        notes_path = self._get_video_output_dir(series_id, video_id) / "notes.json"
        if not notes_path.exists():
            return {"notes": []}

        payload = json.loads(notes_path.read_text(encoding="utf-8"))
        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            raise ValueError("notes.json 格式错误：notes 必须是数组。")

        normalized_notes = []
        for note in notes:
            if not isinstance(note, dict):
                raise ValueError("notes.json 格式错误：note 必须是对象。")
            normalized_notes.append(
                {
                    "id": _require_note_text(note.get("id"), "id"),
                    "title": _require_note_text(note.get("title"), "title"),
                    "content": _require_note_text(note.get("content"), "content"),
                    "source": _require_note_source(note.get("source")),
                    "created_at": _require_note_text(note.get("created_at"), "created_at"),
                    "updated_at": _require_note_text(note.get("updated_at"), "updated_at"),
                }
            )
        return {"notes": normalized_notes}

    def _write_notes_payload(self, series_id: str, video_id: str, payload: dict[str, list[dict[str, str]]]) -> None:
        output_dir = self._get_video_output_dir(series_id, video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "notes.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


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


def _build_chapter_cards(summary: dict[str, object]) -> list[ChapterCardView]:
    cards: list[ChapterCardView] = []

    chapters = summary.get("chapters", [])
    if isinstance(chapters, list):
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            chapter_id = chapter.get("id")
            title = chapter.get("title")
            chapter_summary = chapter.get("summary")
            if not isinstance(chapter_id, str) or not chapter_id.strip():
                continue
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(chapter_summary, str) or not chapter_summary.strip():
                continue
            key_points = chapter.get("key_points", [])
            cards.append(
                ChapterCardView(
                    id=chapter_id,
                    title=title.strip(),
                    summary=chapter_summary.strip(),
                    key_points=[
                        point.strip()
                        for point in key_points
                        if isinstance(point, str) and point.strip()
                    ],
                    start_seconds=_as_seconds(chapter.get("start_seconds")),
                    end_seconds=_as_seconds(chapter.get("end_seconds")),
                    kind="chapter",
                )
            )

    takeaways = summary.get("key_takeaways", [])
    if isinstance(takeaways, list):
        for index, takeaway in enumerate(takeaways, start=1):
            if not isinstance(takeaway, str) or not takeaway.strip():
                continue
            cards.append(
                ChapterCardView(
                    id=f"takeaway-{index}",
                    title=f"关键结论 {index}",
                    summary=takeaway.strip(),
                    key_points=[],
                    start_seconds=None,
                    end_seconds=None,
                    kind="takeaway",
                )
            )

    return cards


def _serialize_knowledge_card(card: KnowledgeCardView) -> dict[str, object]:
    return {
        "id": card.id,
        "title": card.title,
        "kind": card.kind,
        "summary": card.summary,
        "details": card.details,
        "tags": list(card.tags),
        "keywords": list(card.keywords),
        "source_refs": [_serialize_source_ref(item) for item in card.source_refs],
        "related_card_ids": list(card.related_card_ids),
    }


def _serialize_source_ref(source_ref: KnowledgeCardSourceRefView) -> dict[str, object]:
    return {
        "chapter_id": source_ref.chapter_id,
        "start_seconds": source_ref.start_seconds,
        "end_seconds": source_ref.end_seconds,
        "quote": source_ref.quote,
    }


def _to_knowledge_card_view(card_record: dict[str, object]) -> KnowledgeCardView:
    if not isinstance(card_record, dict):
        raise ValueError("knowledge_cards.json 格式错误：card 必须是对象。")
    return KnowledgeCardView(
        id=_require_note_text(card_record.get("id"), "id"),
        title=_require_note_text(card_record.get("title"), "title"),
        kind=_require_knowledge_card_kind(card_record.get("kind")),
        summary=_require_note_text(card_record.get("summary"), "summary"),
        details=_require_note_text(card_record.get("details"), "details"),
        tags=_require_string_list(card_record.get("tags"), "tags"),
        keywords=_require_string_list(card_record.get("keywords"), "keywords"),
        source_refs=_to_source_ref_views(card_record.get("source_refs")),
        related_card_ids=_require_string_list(card_record.get("related_card_ids"), "related_card_ids"),
    )


def _to_source_ref_views(value: object) -> list[KnowledgeCardSourceRefView]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("knowledge_cards.json 格式错误：source_refs 必须是数组。")
    result: list[KnowledgeCardSourceRefView] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("knowledge_cards.json 格式错误：source_ref 必须是对象。")
        chapter_id = item.get("chapter_id")
        quote = item.get("quote")
        if chapter_id is not None and (not isinstance(chapter_id, str) or not chapter_id.strip()):
            raise ValueError("knowledge_cards.json 格式错误：source_ref.chapter_id 不合法。")
        if not isinstance(quote, str):
            raise ValueError("knowledge_cards.json 格式错误：source_ref.quote 不合法。")
        result.append(
            KnowledgeCardSourceRefView(
                chapter_id=chapter_id.strip() if isinstance(chapter_id, str) else None,
                start_seconds=_as_seconds(item.get("start_seconds")),
                end_seconds=_as_seconds(item.get("end_seconds")),
                quote=quote.strip(),
            )
        )
    return result


def _require_string_list(value: object, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"knowledge_cards.json 格式错误：{field_name} 必须是数组。")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"knowledge_cards.json 格式错误：{field_name} 项必须是非空字符串。")
        result.append(item.strip())
    return result


def _require_knowledge_card_kind(value: object) -> str:
    allowed = {"concept", "method", "case", "term", "conclusion"}
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"knowledge_cards.json 格式错误：kind 必须是 {', '.join(sorted(allowed))}。")
    return value


def _to_note_view(note_record: dict[str, str]) -> VideoNoteView:
    return VideoNoteView(
        id=note_record["id"],
        title=note_record["title"],
        content=note_record["content"],
        source=note_record["source"],
        created_at=note_record["created_at"],
        updated_at=note_record["updated_at"],
    )


def _require_note_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"note.{field_name} 不能为空。")
    return value.strip()


def _require_note_source(value: object) -> str:
    if value not in {"manual", "agent"}:
        raise ValueError("note.source 必须是 manual 或 agent。")
    return str(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
