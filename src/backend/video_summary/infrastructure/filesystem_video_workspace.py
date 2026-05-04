from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.agent_graph.evidence.document_schema import SeriesCatalogPayload
from backend.video_summary.library.constants import PLAYGROUND_SERIES_ID
from backend.video_summary.library.models import (
    ChapterCardDTO as ChapterCardDTO,
    KnowledgeCardDTO as KnowledgeCardDTO,
    LibrarySeriesDTO as LibrarySeriesDTO,
    LibraryVideoCardDTO as LibraryVideoCardDTO,
    TranscriptSegmentDTO as TranscriptSegmentDTO,
    VideoChapterCardsDTO as VideoChapterCardsDTO,
    VideoKnowledgeCardsDTO as VideoKnowledgeCardsDTO,
    VideoMindmapDTO as VideoMindmapDTO,
    VideoNoteDTO as VideoNoteDTO,
    VideoNotesDTO as VideoNotesDTO,
    VideoSourceDTO as VideoSourceDTO,
    VideoSummaryDTO as VideoSummaryDTO,
    VideoTranscriptDTO as VideoTranscriptDTO,
    VideoWorkspaceToolsDTO as VideoWorkspaceToolsDTO,
    WorkspaceDTO as WorkspaceDTO,
    WorkspaceToolDTO as WorkspaceToolDTO,
)

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

SERIES_META_FILE = "series_meta.json"
SERIES_CATALOG_FILE = "series_catalog.json"


class FileSystemVideoWorkspace:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._videos_dir = root_dir / "videos"
        self._workspace_dir = root_dir / "workspace"

    def get_workspace(self) -> WorkspaceDTO:
        workspace_id = self._root_dir.name
        return WorkspaceDTO(
            id=workspace_id,
            title=_to_title(workspace_id),
        )

    def list_series(self) -> list[LibrarySeriesDTO]:
        local_series: dict[str, LibrarySeriesDTO] = {}

        if self._videos_dir.exists():
            for series_dir in sorted(self._videos_dir.iterdir()):
                if not series_dir.is_dir():
                    continue
                series_title = self._read_series_title(series_dir.name) or _to_title(series_dir.name)
                local_series[series_dir.name] = LibrarySeriesDTO(
                    id=series_dir.name,
                    title=series_title,
                    videos=self._list_videos_for_series(series_dir),
                )

        if PLAYGROUND_SERIES_ID not in local_series:
            local_series[PLAYGROUND_SERIES_ID] = LibrarySeriesDTO(
                id=PLAYGROUND_SERIES_ID,
                title="Playground",
                videos=[],
                is_linked=False,
                source_url="",
            )

        return list(local_series.values())

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
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
        return VideoSourceDTO(
            series_id=series_id,
            video_id=video_id,
            title=video_path.stem,
            source_name=video_path.name,
            source_path=video_path,
            output_dir=output_dir,
            processed=(output_dir / "summary.json").exists(),
        )

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        summary_path = self._workspace_dir / series_id / video_id / "summary.json"
        if not summary_path.exists():
            return None

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        transcript = _load_transcript_segments(self._workspace_dir / series_id / video_id / "transcript.cleaned.json")
        summary = _attach_chapter_transcript(summary, transcript)
        title = str(summary.get("title", video.title)).strip() or video.title
        return VideoSummaryDTO(
            series_id=series_id,
            video_id=video_id,
            title=title,
            summary=summary,
        )

    def get_series_catalog(self, series_id: str) -> dict[str, object] | None:
        payload_path = self._workspace_dir / series_id / SERIES_CATALOG_FILE
        if not payload_path.exists():
            return None
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        return SeriesCatalogPayload.model_validate(payload).model_dump(mode="json")

    def save_series_catalog(self, series_id: str, payload: dict[str, object]) -> None:
        normalized = SeriesCatalogPayload.model_validate(payload).model_dump(mode="json")
        output_dir = self._workspace_dir / series_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / SERIES_CATALOG_FILE).write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        transcript_path = self._workspace_dir / series_id / video_id / "transcript.cleaned.json"
        if not transcript_path.exists():
            return None

        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        title = str(payload.get("title", video.title)).strip() or video.title
        return VideoTranscriptDTO(
            series_id=series_id,
            video_id=video_id,
            title=title,
            duration_seconds=_as_seconds(payload.get("duration_seconds")),
            segments=[
                TranscriptSegmentDTO(
                    start_seconds=segment["start_seconds"],
                    end_seconds=segment["end_seconds"],
                    text=segment["text"],
                )
                for segment in _normalize_transcript_segments(payload.get("segments"))
            ],
        )

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        mindmap_path = self._get_video_output_dir(series_id, video_id) / "mindmap.json"
        if not mindmap_path.exists():
            return None

        summary = self.get_video_summary(series_id, video_id)
        title = summary.title if summary is not None else video.title
        return VideoMindmapDTO(
            series_id=series_id,
            video_id=video_id,
            title=title,
            mindmap=json.loads(mindmap_path.read_text(encoding="utf-8")),
        )

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        summary = self.get_video_summary(series_id, video_id)
        if summary is None:
            return None

        return VideoChapterCardsDTO(
            series_id=series_id,
            video_id=video_id,
            title=summary.title,
            cards=_build_chapter_cards(summary.summary),
        )

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
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

        return VideoKnowledgeCardsDTO(
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
        cards: list[KnowledgeCardDTO],
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

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        notes_payload = self._read_notes_payload(series_id, video_id)
        return VideoNotesDTO(
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
    ) -> VideoNoteDTO | None:
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
    ) -> VideoNoteDTO | None:
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

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        video = self.get_video_source(series_id, video_id)
        if video is None:
            return None

        summary_exists = (video.output_dir / "summary.json").exists()
        knowledge_cards_exists = (video.output_dir / "knowledge_cards.json").exists()
        mindmap_exists = (video.output_dir / "mindmap.json").exists()
        preview_url = f"/api/videos/{series_id}/{video_id}/preview"
        return VideoWorkspaceToolsDTO(
            series_id=series_id,
            video_id=video_id,
            overview=WorkspaceToolDTO(
                id="overview",
                title="AI概况",
                available=True,
                generated=summary_exists,
                status="ready" if summary_exists else "pending",
            ),
            knowledge_cards=WorkspaceToolDTO(
                id="knowledge-cards",
                title="知识卡片",
                available=summary_exists,
                generated=knowledge_cards_exists,
                status="ready" if knowledge_cards_exists else ("available" if summary_exists else "blocked"),
            ),
            mindmap=WorkspaceToolDTO(
                id="mindmap",
                title="思维导图",
                available=summary_exists,
                generated=mindmap_exists,
                status="ready" if mindmap_exists else ("available" if summary_exists else "blocked"),
            ),
            notes=WorkspaceToolDTO(
                id="notes",
                title="笔记",
                available=True,
                generated=True,
                status="ready",
            ),
            preview=WorkspaceToolDTO(
                id="preview",
                title="视频预览",
                available=True,
                generated=True,
                status="ready",
                preview_url=preview_url,
            ),
            ai_todo="当前已支持 AI 切换概况、知识卡片、笔记和视频预览，并可定位时间点或整理笔记。",
        )

    def import_local_series(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        series_id = _normalize_series_id(title)
        if series_id == PLAYGROUND_SERIES_ID:
            raise ValueError("Playground 请使用单独的“添加 Playground 视频”入口。")
        series_dir = self._videos_dir / series_id
        if series_dir.exists():
            raise ValueError(f"系列已存在：{series_id}")

        try:
            series_dir.mkdir(parents=True, exist_ok=False)
            self._write_series_title(series_id, title.strip())
            self._copy_video_streams(series_dir=series_dir, files=files)
            return LibrarySeriesDTO(
                id=series_id,
                title=title.strip(),
                videos=self._list_videos_for_series(series_dir),
            )
        except Exception:
            if series_dir.exists():
                shutil.rmtree(series_dir)
            meta_path = self._workspace_dir / series_id / SERIES_META_FILE
            if meta_path.exists():
                meta_path.unlink()
            raise

    def import_local_playground_videos(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        series_dir = self._videos_dir / PLAYGROUND_SERIES_ID
        series_dir.mkdir(parents=True, exist_ok=True)
        imported_paths = self._copy_video_streams(series_dir=series_dir, files=files)
        return [self._build_local_video_card(PLAYGROUND_SERIES_ID, path) for path in imported_paths]

    def import_local_series_videos(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        if series_id == PLAYGROUND_SERIES_ID:
            return self.import_local_playground_videos(files=files)
        if not self._series_exists(series_id):
            raise ValueError(f"系列不存在：{series_id}")
        series_dir = self._videos_dir / series_id
        series_dir.mkdir(parents=True, exist_ok=True)
        imported_paths = self._copy_video_streams(series_dir=series_dir, files=files)
        return [self._build_local_video_card(series_id, path) for path in imported_paths]

    def _list_videos_for_series(self, series_dir: Path) -> list[LibraryVideoCardDTO]:
        videos = [path for path in sorted(series_dir.iterdir()) if _is_video_file(path)]
        stems = [path.stem for path in videos]
        duplicate_stems = sorted({stem for stem in stems if stems.count(stem) > 1})
        if duplicate_stems:
            raise ValueError(
                f"Series '{series_dir.name}' contains duplicate video stems: {', '.join(duplicate_stems)}"
            )

        return [self._build_local_video_card(series_dir.name, video_path) for video_path in videos]

    def _build_local_video_card(self, series_id: str, video_path: Path) -> LibraryVideoCardDTO:
        processed = (self._workspace_dir / series_id / video_path.stem / "summary.json").exists()
        return LibraryVideoCardDTO(
            id=video_path.stem,
            title=video_path.stem,
            source_name=video_path.name,
            processed=processed,
            status="ready" if processed else "pending",
        )

    def _copy_video_streams(self, *, series_dir: Path, files: list[tuple[str, object]]) -> list[Path]:
        normalized_files = _normalize_import_files(files)
        existing_stems = {path.stem for path in series_dir.iterdir() if _is_video_file(path)} if series_dir.exists() else set()
        incoming_stems = [Path(filename).stem for filename, _ in normalized_files]
        duplicate_stems = sorted({stem for stem in incoming_stems if incoming_stems.count(stem) > 1})
        if duplicate_stems:
            raise ValueError(f"导入文件存在重复视频名：{', '.join(duplicate_stems)}")
        conflicting_stems = sorted(existing_stems.intersection(incoming_stems))
        if conflicting_stems:
            raise ValueError(f"目标目录中已存在同名视频：{', '.join(conflicting_stems)}")

        copied_paths: list[Path] = []
        for filename, stream in normalized_files:
            target_path = series_dir / filename
            if target_path.exists():
                raise ValueError(f"目标目录中已存在文件：{filename}")
            if hasattr(stream, "seek"):
                stream.seek(0)
            with target_path.open("wb") as handle:
                shutil.copyfileobj(stream, handle)
            copied_paths.append(target_path)
        return copied_paths

    def delete_series(self, series_id: str) -> bool:
        if series_id == PLAYGROUND_SERIES_ID:
            raise ValueError("Playground 不能整体删除，请按视频删除。")

        removed = False
        local_dir = self._videos_dir / series_id
        workspace_dir = self._workspace_dir / series_id

        if local_dir.exists():
            shutil.rmtree(local_dir)
            removed = True

        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
            removed = True

        return removed

    def delete_video(self, series_id: str, video_id: str) -> bool:
        removed = False
        local_dir = self._videos_dir / series_id
        if local_dir.exists():
            matches = [path for path in local_dir.iterdir() if _is_video_file(path) and path.stem == video_id]
            for match in matches:
                match.unlink()
                removed = True

        output_dir = self._workspace_dir / series_id / video_id
        if output_dir.exists():
            shutil.rmtree(output_dir)
            removed = True

        return removed

    def _series_exists(self, series_id: str) -> bool:
        return (self._videos_dir / series_id).exists() or (self._workspace_dir / series_id).exists()

    def _read_series_title(self, series_id: str) -> str | None:
        meta_path = self._workspace_dir / series_id / SERIES_META_FILE
        if not meta_path.exists():
            return None
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        return title.strip()

    def _write_series_title(self, series_id: str, title: str) -> None:
        output_dir = self._workspace_dir / series_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / SERIES_META_FILE).write_text(
            json.dumps({"title": title}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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


def _normalize_series_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("系列名称不能为空。")
    if normalized in {".", ".."}:
        raise ValueError("系列名称不合法。")
    if any(char in normalized for char in '<>:"/\\|?*'):
        raise ValueError('系列名称不能包含 <>:"/\\\\|?* 这些字符。')
    if normalized.endswith(" ") or normalized.endswith("."):
        raise ValueError("系列名称不能以空格或句点结尾。")
    reserved = {
        "con", "prn", "aux", "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
    if normalized.lower() in reserved:
        raise ValueError("系列名称不能使用系统保留字。")
    return normalized


def _normalize_import_files(files: list[tuple[str, object]]) -> list[tuple[str, object]]:
    if not files:
        raise ValueError("至少选择一个视频文件。")
    normalized: list[tuple[str, object]] = []
    for filename, stream in files:
        path = Path(filename or "")
        if not path.name:
            raise ValueError("存在缺少文件名的导入项。")
        if not _is_video_suffix(path.suffix):
            raise ValueError(f"不支持的视频格式：{path.name}")
        normalized.append((path.name, stream))
    return normalized


def _is_video_suffix(suffix: str) -> bool:
    return suffix.lower() in VIDEO_SUFFIXES


def _to_title(raw_value: str) -> str:
    return raw_value.replace("_", " ").replace("-", " ").title()


def _load_transcript_segments(transcript_path: Path) -> list[dict[str, object]]:
    if not transcript_path.exists():
        return []

    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    return _normalize_transcript_segments(payload.get("segments"))


def _normalize_transcript_segments(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    normalized_segments: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        start_seconds = _as_seconds(item.get("start_seconds"))
        end_seconds = _as_seconds(item.get("end_seconds"))
        text = item.get("text")
        if start_seconds is None or end_seconds is None:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        normalized_segments.append(
            {
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "text": text.strip(),
            }
        )
    return normalized_segments


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
        segment_start = segment["start_seconds"]
        segment_end = segment["end_seconds"]
        segment_text = segment["text"]
        if segment_end < start_seconds or segment_start > end_seconds:
            continue

        sliced_segments.append(
            {
                "start_seconds": segment_start,
                "end_seconds": segment_end,
                "text": segment_text,
            }
        )

    return sliced_segments


def _as_seconds(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _build_chapter_cards(summary: dict[str, object]) -> list[ChapterCardDTO]:
    cards: list[ChapterCardDTO] = []

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
                ChapterCardDTO(
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
                ChapterCardDTO(
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


def _serialize_knowledge_card(card: KnowledgeCardDTO) -> dict[str, object]:
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


def _to_knowledge_card_view(card_record: dict[str, object]) -> KnowledgeCardDTO:
    if not isinstance(card_record, dict):
        raise ValueError("knowledge_cards.json 格式错误：card 必须是对象。")
    return KnowledgeCardDTO(
        id=_require_note_text(card_record.get("id"), "id"),
        title=_require_note_text(card_record.get("title"), "title"),
        kind=_require_knowledge_card_kind(card_record.get("kind")),
        summary=_require_note_text(card_record.get("summary"), "summary"),
        details=_require_note_text(card_record.get("details"), "details"),
        tags=_require_string_list(card_record.get("tags"), "tags"),
        keywords=_require_string_list(card_record.get("keywords"), "keywords"),
        related_card_ids=_require_string_list(card_record.get("related_card_ids"), "related_card_ids"),
    )


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
    allowed = {"concept", "method", "case", "term", "conclusion", "insight"}
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"knowledge_cards.json 格式错误：kind 必须是 {', '.join(sorted(allowed))}。")
    return value


def _to_note_view(note_record: dict[str, str]) -> VideoNoteDTO:
    return VideoNoteDTO(
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
