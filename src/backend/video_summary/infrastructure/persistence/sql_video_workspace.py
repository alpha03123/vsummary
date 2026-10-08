"""面向现有库 DTO 的 MySQL 读取实现。"""

from __future__ import annotations

import logging
import mimetypes
import shutil
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from datetime import datetime, timezone
import json
import hashlib
from urllib.parse import quote
from sqlalchemy import bindparam, text
from filelock import FileLock
from backend.video_summary.infrastructure.persistence.execution_context import require_execution_lease, observe_video_version, current_execution_claim
from sqlalchemy.orm import Session, sessionmaker

from backend.core.blob_store import BlobReference, BlobStore, BlobStoreError
from backend.core.errors import ActiveJobConflictError
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.current_content_repository import SqlCurrentContentRepository
from backend.core.ids import new_ulid
from backend.video_summary.infrastructure.persistence.models import Artifact, ExternalMediaReference, MediaObject, OutboxEvent, Video
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from backend.video_summary.infrastructure.persistence.sql_rag_source import SqlRagSourceRepository
from backend.video_summary.generation.renderers import parse_markdown
from backend.video_summary.library.markdown_exports import parse_transcript_markdown
from backend.video_summary.library.models import (
    AiSummaryVisualEvidenceDTO, ChapterCardDTO, KnowledgeCardDTO, LibrarySeriesDTO, LibraryVideoCardDTO, TranscriptSegmentDTO,
    VideoChapterCardsDTO, VideoKnowledgeCardsDTO, VideoMindmapDTO, VideoNoteDTO,
    VideoAiSummaryDTO, VideoAiSummaryVisualEvidenceDTO, VideoNotesDTO, VideoSourceDTO, VideoSummaryDTO, VideoTranscriptDTO, VideoWorkspaceToolsDTO, WorkspaceDTO, WorkspaceToolDTO,
)
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.constants import (
    AUDIO_SUFFIXES,
    BILIBILI_INBOX_SOURCE_KIND,
    BILIBILI_INBOX_TITLE,
    MEDIA_STORAGE_MODES,
    MEDIA_SUFFIXES,
)
from backend.core.citations import CitationReference


LOGGER = logging.getLogger(__name__)

_BROWSER_PREVIEW_KIND = "browser_preview"


class SqlVideoWorkspace:
    """SQL 权威库的读取面；不读取旧 ``workspace`` 目录。"""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        blob_store: BlobStore,
        cache_root: Path,
        workspace_id: str,
        media_processor: FfmpegMediaProcessor | None = None,
        media_preview_enabled: bool = True,
    ) -> None:
        if not workspace_id.strip():
            raise ValueError("SqlVideoWorkspace requires an explicit workspace_id.")
        self._sessions = session_factory
        self._blobs = blob_store
        self._cache_root = cache_root
        self._workspace_id = workspace_id
        self._control = SqlControlPlaneRepository(session_factory)
        self._content = SqlCurrentContentRepository(session_factory)
        self._rag_source = SqlRagSourceRepository(session_factory)
        self._media_processor = media_processor or FfmpegMediaProcessor()
        self._media_preview_enabled = media_preview_enabled
        self._preview_locks: dict[str, Lock] = {}
        self._preview_locks_guard = Lock()

    @property
    def cache_root(self) -> Path:
        return self._cache_root

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._sessions

    @property
    def blob_store(self) -> BlobStore:
        return self._blobs

    @property
    def workspace_id(self) -> str:
        """The ownership boundary bound at composition time."""

        return self._workspace_id

    @staticmethod
    def get_local_workspace_id(session_factory: sessionmaker[Session]) -> str | None:
        with session_factory() as session:
            return session.execute(
                text("SELECT id FROM workspaces WHERE owner_scope_id='local-installation' AND deleted_at IS NULL ORDER BY created_at LIMIT 1")
            ).scalar()

    def get_workspace(self) -> WorkspaceDTO:
        with self._sessions() as session:
            row = session.execute(
                text("SELECT id, title FROM workspaces WHERE id=:workspace AND deleted_at IS NULL"),
                {"workspace": self._workspace_id},
            ).mappings().first()
        if row is None:
            raise LookupError(f"workspace not found '{self._workspace_id}'")
        return WorkspaceDTO(id=row["id"], title=row["title"])

    def list_series(self) -> list[LibrarySeriesDTO]:
        with self._sessions() as session:
            series = session.execute(text("""SELECT s.id,s.title,s.source_kind,s.external_source_url,m.payload AS linked_payload
                FROM series s LEFT JOIN linked_series_metadata m ON m.series_id=s.id
                WHERE s.workspace_id=:workspace AND s.deleted_at IS NULL AND s.import_published=1 ORDER BY s.position,s.created_at"""), {"workspace": self._workspace_id}).mappings().all()
            videos = session.execute(text("""SELECT v.id,v.series_id,v.title,v.source_kind,v.external_source_id,v.content_version,m.blob_key,e.source_path AS external_path,t.video_id AS transcript_video_id,su.video_id AS summary_video_id
                FROM videos v JOIN series s ON s.id=v.series_id LEFT JOIN media_objects m ON m.video_id=v.id AND m.state='ready'
                LEFT JOIN external_media_references e ON e.video_id=v.id
                LEFT JOIN transcripts t ON t.video_id=v.id
                LEFT JOIN summaries su ON su.video_id=v.id
                WHERE s.workspace_id=:workspace AND s.deleted_at IS NULL AND s.import_published=1 AND v.deleted_at IS NULL ORDER BY v.created_at"""), {"workspace": self._workspace_id}).mappings().all()
        by_series: dict[str, list[LibraryVideoCardDTO]] = {row["id"]: [] for row in series}
        linked_videos: dict[tuple[str, str], LinkedVideo] = {}
        for row in series:
            for source in _linked_video_sources(row["linked_payload"]).values():
                linked_videos[(row["id"], source.video_id)] = source
        for video in videos:
            source = linked_videos.get((video["series_id"], video["external_source_id"]))
            linked = video["source_kind"] not in {"video", "audio", "local"} and video["blob_key"] is None and video["external_path"] is None and video["content_version"] == 0 and video["transcript_video_id"] is None
            missing_external = video["external_path"] is not None and not Path(video["external_path"]).is_file()
            source_type = ("audio" if Path(video["external_path"]).suffix.lower() in AUDIO_SUFFIXES else "video") if video["external_path"] is not None else ("video" if linked or source is not None else video["source_kind"])
            by_series.setdefault(video["series_id"], []).append(LibraryVideoCardDTO(
                id=video["id"], title=video["title"], source_name=Path(video["external_path"] or video["blob_key"] or "media").name,
                processed=video["summary_video_id"] is not None, status="source_missing" if missing_external else ("ready" if video["content_version"] > 0 else ("linked" if linked else "pending")),
                has_transcript=video["transcript_video_id"] is not None, source_type=source_type,
                is_linked=linked,
                source_id=source.source_id if source is not None else video["external_source_id"] or "",
                item_index=source.item_index if source is not None else 0,
                source_url=source.source_url if source is not None else "",
                provider=source.provider if source is not None else video["source_kind"] if linked else "",
            ))
        return [
            LibrarySeriesDTO(
                id=row["id"],
                title=row["title"],
                videos=by_series.get(row["id"], []),
                is_linked=row["source_kind"] == "linked",
                is_agent_managed=bool(_json_object(row["linked_payload"]).get("is_agent_managed")) if row["linked_payload"] is not None else False,
                source_url=row["external_source_url"] or "",
                kind=("playground" if row["source_kind"] == "playground" else "bilibili_inbox" if row["source_kind"] == BILIBILI_INBOX_SOURCE_KIND else "standard"),
            )
            for row in series
        ]

    def get_video_title(self, series_id: str, video_id: str) -> str | None:
        """Read owned video identity without opening or materializing its original media."""
        with self._sessions() as session:
            return session.execute(text("""SELECT v.title FROM videos v JOIN series s ON s.id=v.series_id
                WHERE v.id=:video AND s.id=:series AND s.workspace_id=:workspace
                AND v.deleted_at IS NULL AND s.deleted_at IS NULL"""),
                {"video": video_id, "series": series_id, "workspace": self._workspace_id}).scalar()

    def has_source_media(self, series_id: str, video_id: str) -> bool:
        with self._sessions() as session:
            return session.execute(text("""SELECT 1 FROM videos v JOIN series s ON s.id=v.series_id
                WHERE v.id=:video AND s.id=:series AND s.workspace_id=:workspace
                AND v.deleted_at IS NULL AND s.deleted_at IS NULL AND (
                    EXISTS(SELECT 1 FROM media_objects m WHERE m.video_id=v.id AND m.state='ready') OR
                    EXISTS(SELECT 1 FROM external_media_references e WHERE e.video_id=v.id))"""),
                {"video": video_id, "series": series_id, "workspace": self._workspace_id}).scalar() is not None

    def set_media_duration(self, sha256: str, duration_seconds: float) -> None:
        import math
        if not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise ValueError('Media duration must be positive and finite.')
        with self._sessions.begin() as session:
            session.execute(text("""UPDATE videos v JOIN series s ON s.id=v.series_id
                JOIN media_objects m ON m.video_id=v.id SET v.duration_ms=:duration
                WHERE s.workspace_id=:workspace AND m.sha256=:sha AND m.state='ready'"""),
                {'duration': round(duration_seconds*1000), 'workspace': self._workspace_id, 'sha': sha256})

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        with self._sessions() as session:
            row = session.execute(text("""SELECT v.id,v.title,v.source_kind,v.external_source_id,v.content_version,m.blob_key,m.sha256,m.byte_size,m.media_type,e.source_path AS external_path,l.payload AS linked_payload
                FROM videos v JOIN series s ON s.id=v.series_id LEFT JOIN media_objects m ON m.video_id=v.id AND m.state='ready'
                LEFT JOIN external_media_references e ON e.video_id=v.id
                LEFT JOIN linked_series_metadata l ON l.series_id=s.id
                WHERE v.id=:video AND s.id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL AND s.deleted_at IS NULL"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).mappings().first()
        if row is None:
            return None
        observe_video_version(video_id, row["content_version"])
        claim = current_execution_claim()
        media_root = self._cache_root if claim is None else self._cache_root / "attempts" / claim.id / claim.lease_token
        linked_source = _linked_video_sources(row["linked_payload"]).get(row["external_source_id"])
        source_url = linked_source.source_url if linked_source is not None else ""
        if row["external_path"] is not None:
            source_path = Path(row["external_path"])
            if not source_path.is_absolute() or not source_path.is_file():
                return None
            source_type = "audio" if source_path.suffix.lower() in AUDIO_SUFFIXES else "video"
            return VideoSourceDTO(series_id=series_id, video_id=video_id, title=row["title"], source_name=source_path.name, source_type=source_type, source_path=source_path, output_dir=media_root / "jobs" / video_id, processed=row["content_version"] > 0, source_url=source_url)
        if row["blob_key"] is None:
            return None
        filename = Path(row["blob_key"]).name
        reference = BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"])
        try:
            source_path = self._blobs.materialize(reference, task_dir=media_root / "media" / video_id, filename=filename)
        except BlobStoreError:
            LOGGER.exception(
                "failed to materialize video source",
                extra={"series_id": series_id, "video_id": video_id, "blob_key": row["blob_key"]},
            )
            return None
        return VideoSourceDTO(series_id=series_id, video_id=video_id, title=row["title"], source_name=filename, source_type=row["source_kind"], source_path=source_path, output_dir=media_root / "jobs" / video_id, processed=row["content_version"] > 0, source_url=source_url)

    def get_video_preview_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        """返回可快速起播的预览媒体，必要时为历史媒体补建派生 Blob。"""
        if not self._media_preview_enabled:
            return None
        source = self.get_video_source(series_id, video_id)
        if source is None or source.source_path.suffix.lower() in AUDIO_SUFFIXES:
            return source
        if not self._media_processor.needs_browser_playback_optimization(source.source_path):
            return source

        with self._preview_lock(video_id):
            preview_path = self._materialize_browser_preview(video_id)
            if preview_path is None:
                preview_path = self._create_browser_preview(video_id, source.source_path)
        return VideoSourceDTO(
            series_id=source.series_id,
            video_id=source.video_id,
            title=source.title,
            source_name=preview_path.name,
            source_type=source.source_type,
            source_path=preview_path,
            output_dir=source.output_dir,
            processed=source.processed,
            duration_seconds=source.duration_seconds,
            source_url=source.source_url,
        )

    def materialize_artifact(self, *, video_id: str, kind: str, filename: str) -> Path | None:
        if Path(filename).name != filename:
            return None
        with self._sessions() as session:
            row = session.execute(text("""SELECT a.blob_key,a.sha256,a.byte_size,a.media_type FROM artifacts a
                JOIN videos v ON v.id=a.video_id JOIN series s ON s.id=v.series_id
                WHERE a.video_id=:video AND a.kind=:kind AND s.workspace_id=:workspace AND a.blob_key LIKE :suffix
                ORDER BY a.created_at DESC LIMIT 1"""), {"video": video_id, "kind": kind, "workspace": self._workspace_id, "suffix": f"%/{filename}"}).mappings().first()
        if row is None:
            return None
        try:
            return self._blobs.materialize(
                BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"]),
                task_dir=self._cache_root / "artifacts" / video_id / kind,
                filename=filename,
            )
        except BlobStoreError:
            return None

    def list_artifacts(self, *, video_id: str, kind: str) -> list[Path]:
        with self._sessions() as session:
            rows = session.execute(text("""SELECT a.blob_key,a.sha256,a.byte_size,a.media_type FROM artifacts a
                JOIN videos v ON v.id=a.video_id JOIN series s ON s.id=v.series_id
                WHERE a.video_id=:video AND a.kind=:kind AND s.workspace_id=:workspace ORDER BY a.blob_key"""), {"video": video_id, "kind": kind, "workspace": self._workspace_id}).mappings().all()
        return [self._blobs.materialize(BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"]), task_dir=self._cache_root / "artifacts" / video_id / kind, filename=Path(row["blob_key"]).name) for row in rows]

    def save_generated_artifact(self, *, video_id: str, kind: str, source_path: Path, media_type: str, content_version: int | None = None, session=None) -> None:
        """Commit an independent generated asset before its processing directory is removed."""
        if session is None:
            with self._sessions.begin() as transaction:
                return self.save_generated_artifact(video_id=video_id, kind=kind, source_path=source_path,
                    media_type=media_type, content_version=content_version, session=transaction)
        if not source_path.is_file():
            raise ValueError('Generated asset file does not exist.')
        row = session.execute(text("""SELECT v.content_version FROM videos v JOIN series s ON s.id=v.series_id
            WHERE v.id=:video AND s.workspace_id=:workspace AND v.deleted_at IS NULL AND s.deleted_at IS NULL"""),
            {'video': video_id, 'workspace': self._workspace_id}).first()
        if row is None:
            raise LookupError('Video does not exist.')
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        with source_path.open('rb') as stream:
            staged = self._blobs.put_staging(job_id=f'artifact{video_id}', source=stream, content_type=media_type)
        reference = self._blobs.commit(staged, object_key=f'artifacts/{video_id}/{kind}/{digest}/{source_path.name}')
        require_execution_lease(session, self._workspace_id)
        existing = session.execute(text('SELECT id FROM artifacts WHERE blob_key=:key'), {'key': reference.key}).scalar()
        if existing is None:
            session.add(Artifact(id=new_ulid(), workspace_id=self._workspace_id, video_id=video_id,
                content_version=row.content_version if content_version is None else content_version,
                kind=kind, blob_key=reference.key, sha256=reference.sha256,
                byte_size=reference.byte_size, media_type=reference.content_type))

    def get_saved_visual_context(self, series_id: str, video_id: str):
        from backend.video_summary.library.models import VideoAiNoteVisualContextDTO, VideoVisualInputFrameDTO
        if self.get_video_title(series_id, video_id) is None:
            return VideoAiNoteVisualContextDTO(frames=[])
        frames = [VideoVisualInputFrameDTO(chapter_id='saved-frame', timestamp_seconds=float(path.stem),
                  image_filename=path.name, image_path=path)
                  for path in self.list_artifacts(video_id=video_id, kind='note_frame')]
        return VideoAiNoteVisualContextDTO(frames=frames)

    def get_saved_visual_paths(self, series_id: str, video_id: str):
        if self.get_video_title(series_id, video_id) is None:
            raise LookupError('Video does not exist.')
        return self.list_artifacts(video_id=video_id, kind='visual_frame') or self.list_artifacts(video_id=video_id, kind='note_frame')

    def save_binary_artifact(self, *, video_id: str, kind: str, source_path: Path, content_version: int | None = None) -> None:
        if not source_path.is_file() or source_path.suffix.lower() != ".jpg":
            raise ValueError("Only existing JPEG artifact files can be committed.")
        with self._sessions() as session:
            row = session.execute(text("""SELECT v.content_version,v.series_id FROM videos v JOIN series s ON s.id=v.series_id
                WHERE v.id=:video AND s.workspace_id=:workspace AND v.deleted_at IS NULL AND s.deleted_at IS NULL"""), {"video": video_id, "workspace": self._workspace_id}).mappings().first()
        if row is None:
            raise LookupError("Video does not exist.")
        version = row["content_version"] if content_version is None else content_version
        with source_path.open("rb") as stream:
            staged = self._blobs.put_staging(job_id=f"artifact{video_id}", source=stream, content_type="image/jpeg")
        reference = self._blobs.commit(staged, object_key=f"artifacts/{video_id}/{kind}/{new_ulid()}/{source_path.name}")
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            existing = session.execute(text("SELECT id FROM artifacts WHERE video_id=:video AND kind=:kind AND blob_key=:key"), {"video": video_id, "kind": kind, "key": reference.key}).scalar()
            if existing is None:
                session.execute(text("INSERT INTO artifacts (id,workspace_id,video_id,content_version,kind,blob_key,sha256,byte_size,media_type,created_at,updated_at) VALUES (:id,:workspace,:video,:version,:kind,:key,:sha,:size,:type,NOW(),NOW())"), {"id": new_ulid(), "workspace": self._workspace_id, "video": video_id, "version": version, "kind": kind, "key": reference.key, "sha": reference.sha256, "size": reference.byte_size, "type": reference.content_type})

    def clear_generated_artifacts(self, video_id: str) -> None:
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            rows = session.execute(text("""SELECT a.blob_key,a.sha256,a.byte_size,a.media_type FROM artifacts a
                JOIN videos v ON v.id=a.video_id JOIN series s ON s.id=v.series_id
                WHERE a.video_id=:video AND s.workspace_id=:workspace AND a.kind IN ('screenshot','note_frame')"""), {"video": video_id, "workspace": self._workspace_id}).mappings().all()
            session.execute(text("""DELETE a FROM artifacts a JOIN videos v ON v.id=a.video_id JOIN series s ON s.id=v.series_id
                WHERE a.video_id=:video AND s.workspace_id=:workspace AND a.kind IN ('screenshot','note_frame')"""), {"video": video_id, "workspace": self._workspace_id})
        for row in rows:
            self._blobs.delete(BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"]))

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        with self._sessions() as session:
            row = session.execute(text("""SELECT su.title, su.payload,v.content_version FROM summaries su JOIN videos v ON v.id=su.video_id
                JOIN series s ON s.id=v.series_id WHERE su.video_id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).mappings().first()
            segments = session.execute(
                text("SELECT start_ms,end_ms,text FROM transcript_segments WHERE video_id=:video ORDER BY ordinal"),
                {"video": video_id},
            ).mappings().all() if row is not None else []
        if row is None:
            return None
        observe_video_version(video_id, row["content_version"])
        transcript_segments = [
            {
                "start_seconds": segment["start_ms"] / 1000,
                "end_seconds": segment["end_ms"] / 1000,
                "text": segment["text"],
            }
            for segment in segments
        ]
        return VideoSummaryDTO(
            series_id=series_id,
            video_id=video_id,
            title=row["title"],
            summary=_attach_chapter_image_urls(
                _attach_chapter_transcript(_json_object(row["payload"]), transcript_segments),
                series_id=series_id,
                video_id=video_id,
            ),
        )

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        with self._sessions() as session:
            header = session.execute(text("""SELECT v.title,v.content_version,t.duration_ms FROM transcripts t JOIN videos v ON v.id=t.video_id
                JOIN series s ON s.id=v.series_id WHERE t.video_id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).mappings().first()
            if header is None:
                return None
            segments = session.execute(text("SELECT start_ms,end_ms,text FROM transcript_segments WHERE video_id=:video ORDER BY ordinal"), {"video": video_id}).mappings().all()
        observe_video_version(video_id, header["content_version"])
        return VideoTranscriptDTO(series_id=series_id, video_id=video_id, title=header["title"], duration_seconds=(header["duration_ms"] / 1000 if header["duration_ms"] is not None else None), segments=[TranscriptSegmentDTO(start_seconds=row["start_ms"] / 1000, end_seconds=row["end_ms"] / 1000, text=row["text"]) for row in segments])

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        summary = self.get_video_summary(series_id, video_id)
        if summary is None:
            return None
        cards: list[ChapterCardDTO] = []
        for item in _chapters_from_summary(summary.summary):
            payload = item["payload"]
            cards.append(ChapterCardDTO(id=str(payload.get("id") or new_ulid()), title=item["title"], summary=item["body"], key_points=[str(value) for value in payload.get("key_points", []) if isinstance(value, str)], start_seconds=(item["start_ms"] / 1000 if item["start_ms"] is not None else None), end_seconds=(item["end_ms"] / 1000 if item["end_ms"] is not None else None), kind=str(payload.get("kind") or "chapter")))
        return VideoChapterCardsDTO(series_id=series_id, video_id=video_id, title=summary.title, cards=cards)

    def get_video_ai_summary(self, series_id: str, video_id: str) -> VideoAiSummaryDTO | None:
        with self._sessions() as session:
            row = session.execute(text("""SELECT a.title,a.content,a.citations,a.created_at,a.updated_at FROM ai_summaries a JOIN videos v ON v.id=a.video_id
                JOIN series s ON s.id=v.series_id WHERE a.video_id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND a.status='ready'"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).mappings().first()
        if row is None:
            return None
        citations = _json_list_of_objects(row["citations"])
        return VideoAiSummaryDTO(series_id=series_id, video_id=video_id, title=row["title"], content=row["content"], created_at=row["created_at"].isoformat(), updated_at=row["updated_at"].isoformat(), citations=[CitationReference.model_validate(item) for item in citations])

    def get_video_ai_summary_visual_evidence(self, series_id: str, video_id: str) -> VideoAiSummaryVisualEvidenceDTO | None:
        if self.get_video_title(series_id, video_id) is None:
            return None
        with self._sessions() as session:
            rows = session.execute(text("SELECT timestamp_ms,text FROM ai_summary_visual_evidence WHERE video_id=:video ORDER BY ordinal"), {"video": video_id}).mappings().all()
        return VideoAiSummaryVisualEvidenceDTO(series_id=series_id, video_id=video_id, frames=[AiSummaryVisualEvidenceDTO(timestamp_seconds=row["timestamp_ms"] / 1000, text=row["text"]) for row in rows])

    def get_video_visual_evidence(self, series_id: str, video_id: str):
        # Visual evidence is represented by SQL AI-summary evidence and Blob
        # artifacts. The legacy separate JSON payload has no SQL-only consumer.
        return None

    def save_video_ai_summary(self, series_id: str, video_id: str, *, title: str, content: str, citations=None) -> VideoAiSummaryDTO | None:
        if self.get_video_title(series_id, video_id) is None:
            return None
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            session.execute(text("""INSERT INTO ai_summaries (video_id,title,content,citations,status,created_at,updated_at)
                VALUES (:video,:title,:content,CAST(:citations AS JSON),'ready',NOW(),NOW())
                ON DUPLICATE KEY UPDATE title=VALUES(title),content=VALUES(content),citations=VALUES(citations),status='ready',updated_at=NOW()"""), {"video": video_id, "title": title.strip(), "content": content.strip(), "citations": json.dumps([item.model_dump(mode="json") for item in citations] if citations else [])})
            self._enqueue_index_change(session, series_id=series_id, video_id=video_id)
        return self.get_video_ai_summary(series_id, video_id)

    def update_video_ai_summary(self, series_id: str, video_id: str, *, title: str, content: str) -> VideoAiSummaryDTO | None:
        if self.get_video_ai_summary(series_id, video_id) is None:
            return None
        return self.save_video_ai_summary(series_id, video_id, title=title, content=content)

    def save_video_ai_summary_visual_evidence(self, series_id: str, video_id: str, *, frames: list[AiSummaryVisualEvidenceDTO]) -> None:
        if self.get_video_title(series_id, video_id) is None:
            raise ValueError("Video does not exist.")
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            session.execute(text("DELETE FROM ai_summary_visual_evidence WHERE video_id=:video"), {"video": video_id})
            for ordinal, frame in enumerate(frames):
                session.execute(text("INSERT INTO ai_summary_visual_evidence (id,video_id,ordinal,timestamp_ms,text) VALUES (:id,:video,:ordinal,:timestamp,:text)"), {"id": new_ulid(), "video": video_id, "ordinal": ordinal, "timestamp": round(frame.timestamp_seconds * 1000), "text": frame.text})
            self._enqueue_index_change(session, series_id=series_id, video_id=video_id)

    def save_video_mindmap(self, series_id: str, video_id: str, *, mindmap: dict[str, Any]) -> None:
        if self.get_video_title(series_id, video_id) is None:
            raise ValueError("Video does not exist.")
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            version = session.execute(text("SELECT content_version FROM videos WHERE id=:video"), {"video": video_id}).scalar_one()
            session.execute(text("""INSERT INTO mindmaps (id,video_id,content_version,title,payload,row_version,created_at,updated_at)
                VALUES (:id,:video,:version,:title,CAST(:payload AS JSON),1,NOW(),NOW())
                ON DUPLICATE KEY UPDATE content_version=VALUES(content_version),title=VALUES(title),payload=VALUES(payload),row_version=row_version+1,updated_at=NOW()"""), {"id": new_ulid(), "video": video_id, "version": version, "title": self.get_video_title(series_id, video_id), "payload": json.dumps(mindmap, ensure_ascii=False)})

    def save_series_catalog(self, series_id: str, payload: dict[str, object]) -> None:
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            exists = session.execute(text("SELECT 1 FROM series WHERE id=:series AND workspace_id=:workspace AND deleted_at IS NULL"), {"series": series_id, "workspace": self._workspace_id}).scalar()
            if exists is None:
                raise LookupError("Series does not exist.")
            session.execute(text("""INSERT INTO series_catalogs (series_id,payload,created_at,updated_at) VALUES (:series,CAST(:payload AS JSON),NOW(),NOW())
                ON DUPLICATE KEY UPDATE payload=VALUES(payload),updated_at=NOW()"""), {"series": series_id, "payload": json.dumps(payload, ensure_ascii=False)})

    def save_series_mindmap(self, series_id: str, *, mindmap: dict[str, Any]) -> None:
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            title = session.execute(text("SELECT title FROM series WHERE id=:series AND workspace_id=:workspace AND deleted_at IS NULL"), {"series": series_id, "workspace": self._workspace_id}).scalar_one()
            session.execute(text("""INSERT INTO mindmaps (id,series_id,title,payload,row_version,created_at,updated_at)
                VALUES (:id,:series,:title,CAST(:payload AS JSON),1,NOW(),NOW())
                ON DUPLICATE KEY UPDATE title=VALUES(title),payload=VALUES(payload),row_version=row_version+1,updated_at=NOW()"""), {"id": new_ulid(), "series": series_id, "title": title, "payload": json.dumps(mindmap, ensure_ascii=False)})

    def get_series_dir(self, series_id: str) -> Path:
        # Compatibility for media workflows that require a temporary directory.
        # It is not a persisted artifact location.
        target = self._cache_root / "series-work" / series_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_linked_series(self, series_id: str) -> LinkedSeries | None:
        with self._sessions() as session:
            row = session.execute(text("SELECT s.title,m.payload FROM linked_series_metadata m JOIN series s ON s.id=m.series_id WHERE s.id=:series AND s.workspace_id=:workspace AND s.deleted_at IS NULL"), {"series": series_id, "workspace": self._workspace_id}).mappings().first()
        if row is None:
            return None
        payload = _json_object(row["payload"])
        return LinkedSeries(series_id=series_id, title=row["title"], cover_url=str(payload.get("cover_url") or ""), source_url=str(payload.get("source_url") or ""), is_agent_managed=bool(payload.get("is_agent_managed")), videos=[_linked_video_from_payload(item) for item in payload.get("videos", []) if isinstance(item, dict)])

    def get_linked_video_for_download(self, series_id: str, video_id: str) -> LinkedVideo | None:
        """将库内 ULID 映射为链接元数据中用于下载的平台 ID。"""

        linked_series = self.get_linked_series(series_id)
        if linked_series is None:
            return None
        direct = next((item for item in linked_series.videos if item.video_id == video_id), None)
        if direct is not None:
            return direct
        with self._sessions() as session:
            external_source_id = session.execute(
                text("""SELECT v.external_source_id FROM videos v JOIN series s ON s.id=v.series_id
                    WHERE v.id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""),
                {"video": video_id, "series": series_id, "workspace": self._workspace_id},
            ).scalar()
        if not isinstance(external_source_id, str) or not external_source_id:
            return None
        return next((item for item in linked_series.videos if item.video_id == external_source_id), None)

    def save_linked_series(self, series: LinkedSeries) -> None:
        workspace_id = self._workspace_id
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            existing = session.execute(text("SELECT id FROM series WHERE id=:series AND workspace_id=:workspace"), {"series": series.series_id, "workspace": workspace_id}).scalar()
            if existing is None:
                position = int(session.execute(text("SELECT COALESCE(MAX(position),-1)+1 FROM series WHERE workspace_id=:workspace"), {"workspace": workspace_id}).scalar_one())
                session.execute(text("INSERT INTO series (id,workspace_id,title,position,source_kind,external_source_url,row_version,created_at,updated_at) VALUES (:id,:workspace,:title,:position,'linked',:url,1,NOW(),NOW())"), {"id": series.series_id, "workspace": workspace_id, "title": series.title, "position": position, "url": series.source_url})
            else:
                session.execute(text("UPDATE series SET title=:title,external_source_url=:url,updated_at=NOW() WHERE id=:id AND workspace_id=:workspace"), {"id": series.series_id, "title": series.title, "url": series.source_url, "workspace": workspace_id})
            for item in series.videos:
                external_source_id = item.video_id
                existing_video = session.execute(
                text("""SELECT v.id,v.deleted_at FROM videos v JOIN series s ON s.id=v.series_id
                    WHERE v.series_id=:series AND s.workspace_id=:workspace AND v.external_source_id=:external"""),
                    {"series": series.series_id, "workspace": workspace_id, "external": external_source_id},
                ).mappings().first()
                if existing_video is None:
                    session.add(
                        Video(
                            id=new_ulid(),
                            series_id=series.series_id,
                            title=item.title,
                            source_kind=item.provider,
                            external_source_id=external_source_id,
                            duration_ms=item.duration_seconds * 1000,
                        )
                    )
                elif existing_video["deleted_at"] is not None:
                    _clear_deleted_video_content(session, video_id=existing_video["id"])
                    session.execute(
                        text("""UPDATE videos
                            SET deleted_at=NULL,title=:title,source_kind=:kind,duration_ms=:duration,
                                content_version=0,row_version=row_version+1,updated_at=NOW()
                            WHERE id=:id"""),
                        {"id": existing_video["id"], "title": item.title, "kind": item.provider, "duration": item.duration_seconds * 1000},
                    )
                else:
                    session.execute(
                        text("UPDATE videos SET title=:title,source_kind=:kind,duration_ms=:duration,row_version=row_version+1,updated_at=NOW() WHERE id=:id"),
                        {"id": existing_video["id"], "title": item.title, "kind": item.provider, "duration": item.duration_seconds * 1000},
                    )
            payload = {"cover_url": series.cover_url, "source_url": series.source_url, "is_agent_managed": series.is_agent_managed, "videos": [item.__dict__ for item in series.videos]}
            session.execute(text("INSERT INTO linked_series_metadata (series_id,payload,created_at,updated_at) VALUES (:series,CAST(:payload AS JSON),NOW(),NOW()) ON DUPLICATE KEY UPDATE payload=VALUES(payload),updated_at=NOW()"), {"series": series.series_id, "payload": json.dumps(payload, ensure_ascii=False)})

    def delete_linked_series(self, series_id: str) -> bool:
        return self.delete_series(series_id)

    def relink_external_video(self, *, series_id: str, video_id: str, source_path: Path) -> None:
        if not source_path.is_absolute() or not source_path.is_file() or source_path.suffix.lower() not in MEDIA_SUFFIXES:
            raise ValueError("Relink source must be an existing absolute media file.")
        with self._sessions() as session:
            resolved_video_id = session.execute(
                text("""SELECT v.id FROM videos v JOIN series s ON s.id=v.series_id
                    WHERE v.id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""),
                {"video": video_id, "series": series_id, "workspace": self._workspace_id},
            ).scalar()
            if resolved_video_id is None:
                resolved_video_id = session.execute(
                text("""SELECT v.id FROM videos v JOIN series s ON s.id=v.series_id
                    WHERE v.external_source_id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""),
                {"video": video_id, "series": series_id, "workspace": self._workspace_id},
                ).scalar()
        if resolved_video_id is None:
            raise LookupError("Linked video does not exist.")
        self._delete_browser_previews(resolved_video_id)
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            external = session.get(ExternalMediaReference, resolved_video_id)
            if external is not None:
                external.source_path = str(source_path)
        if external is not None:
            self._prepare_browser_preview(resolved_video_id, source_path)
            return
        with source_path.open("rb") as stream:
            staged = self._blobs.put_staging(job_id=f"relink{resolved_video_id}", source=stream, content_type="application/octet-stream")
        reference = self._blobs.commit(staged, object_key=f"media/{resolved_video_id}/source{source_path.suffix.lower()}")
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            session.execute(text("DELETE FROM media_objects WHERE video_id=:video"), {"video": resolved_video_id})
            session.add(MediaObject(id=new_ulid(), video_id=resolved_video_id, blob_key=reference.key, media_type=reference.content_type, byte_size=reference.byte_size, sha256=reference.sha256, state="ready"))
        self._prepare_browser_preview(resolved_video_id, source_path)

    def attach_downloaded_file(self, series_id: str, video_id: str, source_path: Path) -> None:
        self.relink_external_video(series_id=series_id, video_id=video_id, source_path=source_path)
        source_path.unlink(missing_ok=True)

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        if self.get_video_title(series_id, video_id) is None:
            return None
        has_media = self._media_preview_enabled and self.has_source_media(series_id, video_id)
        summary = self.get_video_summary(series_id, video_id)
        transcript = self.get_video_transcript(series_id, video_id)
        cards = self.get_video_knowledge_cards(series_id, video_id)
        mindmap = self.get_video_mindmap(series_id, video_id)
        ai_summary = self.get_video_ai_summary(series_id, video_id)
        ready = lambda value: "ready" if value else "pending"
        return VideoWorkspaceToolsDTO(series_id=series_id, video_id=video_id, overview=WorkspaceToolDTO(id="overview", title="AI整理逐字稿", available=True, generated=summary is not None, status=ready(summary)), ai_summary=WorkspaceToolDTO(id="ai-summary", title="AI概括", available=True, generated=ai_summary is not None, status=ready(ai_summary)), knowledge_cards=WorkspaceToolDTO(id="knowledge-cards", title="知识卡片", available=summary is not None, generated=bool(cards and cards.cards), status="ready" if cards and cards.cards else ("available" if summary else "blocked")), mindmap=WorkspaceToolDTO(id="mindmap", title="思维导图", available=summary is not None, generated=mindmap is not None, status="ready" if mindmap else ("available" if summary else "blocked")), notes=WorkspaceToolDTO(id="notes", title="笔记", available=True, generated=bool(self.get_video_notes(series_id, video_id).notes), status="ready"), preview=WorkspaceToolDTO(id="preview", title="视频预览", available=has_media, generated=has_media, status="ready" if has_media else "unavailable", preview_url=f"/api/videos/{series_id}/{video_id}/preview" if has_media else None, subtitle_url=f"/api/videos/{series_id}/{video_id}/subtitles.vtt" if transcript is not None else None), ai_todo="继续生成可用内容。")

    def import_local_series_from_paths(self, *, title: str, source_paths: list[Path], storage_mode: str = "copy") -> LibrarySeriesDTO:
        workspace_id = self._workspace_id
        if not title.strip() or not source_paths:
            raise ValueError("A workspace, non-empty title, and media files are required.")
        self._validate_import_paths(source_paths, storage_mode)
        series_id = self._control.create_series_at_next_position(
            workspace_id=workspace_id,
            title=title.strip(),
            source_kind="local",
            storage_mode=storage_mode,
        )
        self._import_paths(series_id, source_paths, storage_mode=storage_mode)
        return next(item for item in self.list_series() if item.id == series_id)

    def can_hardlink(self, source_path: Path) -> bool:
        return self._blobs.can_hardlink(source_path)

    def import_local_series_videos_from_paths(self, *, series_id: str, source_paths: list[Path]) -> list[LibraryVideoCardDTO]:
        with self._sessions() as session:
            storage_mode = session.execute(text("SELECT storage_mode FROM series WHERE id=:series AND workspace_id=:workspace AND deleted_at IS NULL"), {"series": series_id, "workspace": self._workspace_id}).scalar()
        if storage_mode is None:
            raise LookupError("Series does not exist.")
        self._import_paths(series_id, source_paths, storage_mode=storage_mode)
        return next(item.videos for item in self.list_series() if item.id == series_id)

    def ensure_playground_series(self) -> str:
        return self._control.ensure_playground_series(workspace_id=self._workspace_id)

    def ensure_bilibili_inbox_series(self) -> str:
        return self._control.ensure_series_by_source_kind(
            workspace_id=self._workspace_id,
            source_kind=BILIBILI_INBOX_SOURCE_KIND,
            title=BILIBILI_INBOX_TITLE,
        )

    def import_local_playground_videos_from_paths(self, *, source_paths: list[Path]) -> list[LibraryVideoCardDTO]:
        return self.import_local_series_videos_from_paths(
            series_id=self.ensure_playground_series(), source_paths=source_paths,
        )

    def rename_series(self, series_id: str, title: str) -> bool:
        if not title.strip():
            raise ValueError("Series title is required.")
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            result = session.execute(text("UPDATE series SET title=:title,row_version=row_version+1,updated_at=NOW() WHERE id=:id AND workspace_id=:workspace AND deleted_at IS NULL"), {"id": series_id, "workspace": self._workspace_id, "title": title.strip()})
            if result.rowcount == 1:
                self._enqueue_index_change(session, series_id=series_id, event_type="series_changed")
        return result.rowcount == 1

    def rename_video(self, series_id: str, video_id: str, title: str) -> bool:
        if not title.strip():
            raise ValueError("Video title is required.")
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            result = session.execute(text("""UPDATE videos SET title=:title,row_version=row_version+1,updated_at=NOW()
                WHERE id=:video AND series_id=:series AND deleted_at IS NULL AND EXISTS
                (SELECT 1 FROM series s WHERE s.id=:series AND s.workspace_id=:workspace AND s.deleted_at IS NULL)"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id, "title": title.strip()})
            if result.rowcount == 1:
                self._enqueue_index_change(session, series_id=series_id, video_id=video_id, event_type="video_changed")
        return result.rowcount == 1

    def delete_video(self, series_id: str, video_id: str) -> bool:
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            owned_series = session.execute(text("SELECT id FROM series WHERE id=:series AND workspace_id=:workspace AND deleted_at IS NULL FOR UPDATE"),
                {"series": series_id, "workspace": self._workspace_id}).scalar()
            if owned_series is None:
                return False
            owned_video = session.execute(text("SELECT id FROM videos WHERE id=:video AND series_id=:series AND deleted_at IS NULL FOR UPDATE"),
                {"video": video_id, "series": series_id}).scalar()
            if owned_video is None:
                return False
            active_job = session.execute(text("""SELECT id FROM jobs
                WHERE workspace_id=:workspace AND resource_id IN (:video,:series)
                AND status IN ('queued','retrying','running','cancelling') LIMIT 1"""), {"workspace": self._workspace_id, "video": video_id, "series": series_id}).scalar()
            if active_job is not None:
                raise ActiveJobConflictError(f"视频 '{series_id}/{video_id}' 有活跃任务，不能删除。")
            rows = session.execute(text("""SELECT m.blob_key,m.sha256,m.byte_size,m.media_type FROM media_objects m
                JOIN videos v ON v.id=m.video_id JOIN series s ON s.id=v.series_id
                WHERE m.video_id=:video AND v.series_id=:series AND s.workspace_id=:workspace
                UNION ALL
                SELECT a.blob_key,a.sha256,a.byte_size,a.media_type FROM artifacts a
                JOIN videos v ON v.id=a.video_id JOIN series s ON s.id=v.series_id
                WHERE a.video_id=:video AND v.series_id=:series AND s.workspace_id=:workspace"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).mappings().all()
            cleanup = self._prepare_resource_cleanup(session, rows=rows, video_ids=[video_id])
            self._delete_video_rows(session, video_id)
            self._enqueue_index_change(session, series_id=series_id, video_id=video_id, event_type="video_deleted")
        self.delete_resource_files(cleanup)
        return True

    def delete_series(self, series_id: str) -> bool:
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            owned_series = session.execute(text("SELECT id FROM series WHERE id=:series AND workspace_id=:workspace AND deleted_at IS NULL FOR UPDATE"), {"series": series_id, "workspace": self._workspace_id}).scalar()
            if owned_series is None:
                return False
            active_job = session.execute(text("""SELECT j.id FROM jobs j
                WHERE j.workspace_id=:workspace AND j.status IN ('queued','retrying','running','cancelling')
                AND (j.resource_id=:series OR j.resource_id IN (SELECT id FROM videos WHERE series_id=:series))
                LIMIT 1"""), {"workspace": self._workspace_id, "series": series_id}).scalar()
            if active_job is not None:
                raise ActiveJobConflictError(f"系列 '{series_id}' 有活跃任务，不能删除。")
            video_ids = list(session.execute(text("SELECT id FROM videos WHERE series_id=:series ORDER BY id FOR UPDATE"), {"series": series_id}).scalars())
            rows = session.execute(text("""SELECT m.blob_key,m.sha256,m.byte_size,m.media_type FROM media_objects m
                JOIN videos v ON v.id=m.video_id JOIN series s ON s.id=v.series_id
                WHERE v.series_id=:series AND s.workspace_id=:workspace
                UNION ALL
                SELECT a.blob_key,a.sha256,a.byte_size,a.media_type FROM artifacts a
                WHERE a.workspace_id=:workspace AND (a.series_id=:series OR a.video_id IN
                (SELECT id FROM videos WHERE series_id=:series))"""), {"series": series_id, "workspace": self._workspace_id}).mappings().all()
            cleanup = self._prepare_resource_cleanup(session, rows=rows, video_ids=video_ids, series_id=series_id)
            for video_id in video_ids:
                self._delete_video_rows(session, video_id)
                self._enqueue_index_change(session, series_id=series_id, video_id=video_id, event_type="video_deleted")
            session.execute(text("DELETE FROM artifacts WHERE series_id=:series"), {"series": series_id})
            session.execute(text("DELETE FROM series WHERE id=:series"), {"series": series_id})
            self._enqueue_index_change(session, series_id=series_id, event_type="series_deleted")
        self.delete_resource_files(cleanup)
        return True

    @staticmethod
    def _delete_video_rows(session: Session, video_id: str) -> None:
        # Remove restrictive references first; the remaining content uses FK cascades.
        for table in ("transcripts", "artifacts", "external_media_references", "media_objects", "videos"):
            column = "id" if table == "videos" else "video_id"
            session.execute(text(f"DELETE FROM {table} WHERE {column}=:video"), {"video": video_id})

    def _prepare_resource_cleanup(self, session: Session, *, rows, video_ids: list[str],
        series_id: str | None = None) -> dict[str, Any]:
        job_ids = list(session.execute(text("""SELECT id FROM jobs WHERE workspace_id=:workspace
            AND (resource_id=:series OR resource_id IN :videos)""").bindparams(
                bindparam("videos", expanding=True)),
            {"workspace": self._workspace_id, "series": series_id, "videos": video_ids}).scalars())
        cleanup = {"blobs": [dict(row) for row in rows], "video_ids": video_ids,
            "series_id": series_id, "job_ids": job_ids}
        _enqueue_outbox_event(session, workspace_id=self._workspace_id, aggregate_type="resource",
            aggregate_id=series_id or video_ids[0], event_type="resource_cleanup_requested",
            payload=cleanup, occurred_at=datetime.now(timezone.utc))
        return cleanup

    def delete_resource_files(self, cleanup: dict[str, Any]) -> None:
        """Idempotent file cleanup, retried by Outbox after the SQL transaction commits."""
        for row in cleanup["blobs"]:
            self._blobs.delete(BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"]))
        paths = [self._cache_root / kind / video_id
            for video_id in cleanup["video_ids"]
            for kind in ("media", "jobs", "artifacts", "previews", "preview-staging", "generation-stages")]
        paths.extend(self._cache_root / "attempts" / job_id for job_id in cleanup["job_ids"])
        if cleanup["series_id"] is not None:
            paths.append(self._cache_root / "series-work" / cleanup["series_id"])
        root = self._cache_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        # The request and Outbox may clean the same directories concurrently.
        with FileLock(root / "resource-cleanup.lock"):
            for path in paths:
                path.resolve().relative_to(root)
                if path.exists():
                    shutil.rmtree(path)

    def _validate_import_paths(self, source_paths: list[Path], storage_mode: str) -> None:
        if storage_mode not in MEDIA_STORAGE_MODES:
            raise ValueError(f"Unsupported media storage mode: {storage_mode}")
        for source_path in source_paths:
            if not source_path.is_absolute() or not source_path.is_file() or source_path.suffix.lower() not in MEDIA_SUFFIXES:
                raise ValueError(f"Media path is invalid: {source_path}")
            if storage_mode == "hardlink" and not self._blobs.can_hardlink(source_path):
                raise ValueError(f"Hard links require source and Blob storage on the same volume: {source_path}")

    def _import_paths(self, series_id: str, source_paths: list[Path], storage_mode: str = "copy") -> None:
        self._validate_import_paths(source_paths, storage_mode)
        with self._sessions() as session:
            exists = session.execute(text("SELECT 1 FROM series WHERE id=:series AND workspace_id=:workspace AND deleted_at IS NULL"), {"series": series_id, "workspace": self._workspace_id}).scalar()
        if exists is None:
            raise LookupError("Series does not exist.")
        for source_path in source_paths:
            digest = _sha256_path(source_path)
            video_id = self._control.create_video(series_id=series_id, title=source_path.stem, source_kind="audio" if source_path.suffix.lower() in AUDIO_SUFFIXES else "video", external_source_id=digest)
            if storage_mode == "external_reference":
                with self._sessions.begin() as session:
                    require_execution_lease(session, self._workspace_id)
                    session.add(ExternalMediaReference(video_id=video_id, source_path=str(source_path)))
                self._prepare_browser_preview(video_id, source_path)
                continue
            if storage_mode == "hardlink":
                staged = self._blobs.put_staging_hardlink(job_id=f"import{video_id}", source_path=source_path, content_type="application/octet-stream")
            else:
                with source_path.open("rb") as stream:
                    staged = self._blobs.put_staging(job_id=f"import{video_id}", source=stream, content_type="application/octet-stream")
            reference = self._blobs.commit(staged, object_key=f"media/{video_id}/source{source_path.suffix.lower()}")
            with self._sessions.begin() as session:
                require_execution_lease(session, self._workspace_id)
                session.add(MediaObject(id=new_ulid(), video_id=video_id, blob_key=reference.key, media_type=reference.content_type, byte_size=reference.byte_size, sha256=reference.sha256, state="ready"))
            self._prepare_browser_preview(video_id, source_path)

    def _prepare_browser_preview(self, video_id: str, source_path: Path) -> None:
        if not self._media_preview_enabled:
            return
        """在导入或下载期间预建有尾部索引或分片的 MP4 预览副本。"""
        if not self._media_processor.needs_browser_playback_optimization(source_path):
            return
        with self._preview_lock(video_id):
            self._create_browser_preview(video_id, source_path)

    def _create_browser_preview(self, video_id: str, source_path: Path) -> Path:
        """无损重封装独立副本，绝不改写原始媒体或硬链接源文件。"""
        staging_dir = self._cache_root / "preview-staging" / video_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        preview_path = staging_dir / f".{uuid4().hex}.preview{source_path.suffix.lower()}"
        try:
            shutil.copyfile(source_path, preview_path)
            self._media_processor.ensure_browser_playable_mp4(preview_path)
            reference = self._commit_browser_preview(video_id, preview_path)
            return self._blobs.materialize(
                reference,
                task_dir=self._cache_root / "previews" / video_id,
                filename=Path(reference.key).name,
            )
        finally:
            preview_path.unlink(missing_ok=True)

    def _commit_browser_preview(self, video_id: str, preview_path: Path) -> BlobReference:
        media_type, _ = mimetypes.guess_type(preview_path.name)
        with preview_path.open("rb") as stream:
            staged = self._blobs.put_staging(
                job_id=f"preview{video_id}",
                source=stream,
                content_type=media_type or "video/mp4",
            )
        reference = self._blobs.commit(
            staged,
            object_key=f"artifacts/{video_id}/{_BROWSER_PREVIEW_KIND}/preview{preview_path.suffix.lower()}",
        )
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            session.add(
                Artifact(
                    id=new_ulid(),
                    workspace_id=self._workspace_id,
                    video_id=video_id,
                    content_version=None,
                    kind=_BROWSER_PREVIEW_KIND,
                    blob_key=reference.key,
                    sha256=reference.sha256,
                    byte_size=reference.byte_size,
                    media_type=reference.content_type,
                )
            )
        return reference

    def _materialize_browser_preview(self, video_id: str) -> Path | None:
        with self._sessions() as session:
            row = session.execute(text("""SELECT a.blob_key,a.sha256,a.byte_size,a.media_type FROM artifacts a
                JOIN videos v ON v.id=a.video_id JOIN series s ON s.id=v.series_id
                WHERE a.video_id=:video AND a.kind=:kind AND s.workspace_id=:workspace
                ORDER BY a.created_at DESC LIMIT 1"""), {"video": video_id, "kind": _BROWSER_PREVIEW_KIND, "workspace": self._workspace_id}).mappings().first()
        if row is None:
            return None
        try:
            return self._blobs.materialize(
                BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"]),
                task_dir=self._cache_root / "previews" / video_id,
                filename=Path(row["blob_key"]).name,
            )
        except BlobStoreError:
            LOGGER.exception("failed to materialize browser preview", extra={"video_id": video_id})
            return None

    def _delete_browser_previews(self, video_id: str) -> None:
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            rows = session.execute(text("""SELECT a.blob_key,a.sha256,a.byte_size,a.media_type FROM artifacts a
                JOIN videos v ON v.id=a.video_id JOIN series s ON s.id=v.series_id
                WHERE a.video_id=:video AND a.kind=:kind AND s.workspace_id=:workspace"""), {"video": video_id, "kind": _BROWSER_PREVIEW_KIND, "workspace": self._workspace_id}).mappings().all()
            session.execute(text("DELETE FROM artifacts WHERE video_id=:video AND kind=:kind"), {"video": video_id, "kind": _BROWSER_PREVIEW_KIND})
        for row in rows:
            self._blobs.delete(BlobReference(row["blob_key"], row["sha256"], row["byte_size"], row["media_type"]))

    def _preview_lock(self, video_id: str) -> Lock:
        with self._preview_locks_guard:
            return self._preview_locks.setdefault(video_id, Lock())

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        with self._sessions() as session:
            title = session.execute(text("""SELECT v.title FROM videos v JOIN series s ON s.id=v.series_id
                WHERE v.id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).scalar()
            if title is None:
                return None
            rows = session.execute(text("SELECT id,title,kind,summary,details,tags,keywords,related_card_ids FROM knowledge_cards WHERE video_id=:video ORDER BY ordinal"), {"video": video_id}).mappings().all()
        return VideoKnowledgeCardsDTO(series_id=series_id, video_id=video_id, title=title, cards=[KnowledgeCardDTO(id=row["id"], title=row["title"], kind=row["kind"], summary=row["summary"], details=row["details"], tags=_json_list(row["tags"]), keywords=_json_list(row["keywords"]), related_card_ids=_json_list(row["related_card_ids"])) for row in rows])

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        with self._sessions() as session:
            title = session.execute(text("""SELECT v.title FROM videos v JOIN series s ON s.id=v.series_id
                WHERE v.id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).scalar()
            if title is None:
                return None
            rows = session.execute(text("SELECT id,title,content,source,created_at,updated_at FROM notes WHERE video_id=:video AND deleted_at IS NULL AND source='manual' ORDER BY updated_at DESC"), {"video": video_id}).mappings().all()
        return VideoNotesDTO(series_id=series_id, video_id=video_id, title=title, notes=[VideoNoteDTO(id=row["id"], title=row["title"], content=row["content"], source=row["source"], created_at=row["created_at"].isoformat(), updated_at=row["updated_at"].isoformat()) for row in rows])

    def create_video_note(self, series_id: str, video_id: str, *, title: str, content: str, source: str) -> VideoNoteDTO | None:
        if not title.strip() or not content.strip() or source not in {"manual", "agent"}:
            raise ValueError("Invalid note payload.")
        if self.get_video_title(series_id, video_id) is None:
            return None
        note_id, now = new_ulid(), datetime.now(timezone.utc)
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            session.execute(text("INSERT INTO notes (id,video_id,title,content,source,row_version,created_at,updated_at) VALUES (:id,:video,:title,:content,:source,1,:now,:now)"), {"id": note_id, "video": video_id, "title": title.strip(), "content": content.strip(), "source": source, "now": now})
            _enqueue_outbox_event(
                session,
                workspace_id=self._workspace_id,
                aggregate_type="note",
                aggregate_id=note_id,
                event_type="note_published",
                payload={"video_id": video_id},
                occurred_at=now,
            )
        self._refresh_rag(series_id, video_id)
        return VideoNoteDTO(id=note_id, title=title.strip(), content=content.strip(), source=source, created_at=now.isoformat(), updated_at=now.isoformat())

    def update_video_note(self, series_id: str, video_id: str, note_id: str, *, title: str, content: str) -> VideoNoteDTO | None:
        if not title.strip() or not content.strip() or self.get_video_title(series_id, video_id) is None:
            return None
        now = datetime.now(timezone.utc)
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            result = session.execute(text("UPDATE notes SET title=:title,content=:content,row_version=row_version+1,updated_at=:now WHERE id=:id AND video_id=:video AND deleted_at IS NULL"), {"id": note_id, "video": video_id, "title": title.strip(), "content": content.strip(), "now": now})
            if result.rowcount != 1:
                return None
            created_at = session.execute(
                text("SELECT created_at FROM notes WHERE id=:id AND video_id=:video AND deleted_at IS NULL"),
                {"id": note_id, "video": video_id},
            ).scalar_one()
            _enqueue_outbox_event(
                session,
                workspace_id=self._workspace_id,
                aggregate_type="note",
                aggregate_id=note_id,
                event_type="note_published",
                payload={"video_id": video_id},
                occurred_at=now,
            )
        self._refresh_rag(series_id, video_id)
        return VideoNoteDTO(id=note_id, title=title.strip(), content=content.strip(), source="manual", created_at=created_at.isoformat(), updated_at=now.isoformat())

    def delete_video_note(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        if self.get_video_title(series_id, video_id) is None:
            return None
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            result = session.execute(text("UPDATE notes SET deleted_at=:now,row_version=row_version+1 WHERE id=:id AND video_id=:video AND deleted_at IS NULL"), {"id": note_id, "video": video_id, "now": datetime.now(timezone.utc)})
            if result.rowcount == 1:
                self._enqueue_index_change(session, series_id=series_id, video_id=video_id, event_type="note_published")
        changed = result.rowcount == 1
        if changed:
            self._refresh_rag(series_id, video_id)
        return changed

    def _enqueue_index_change(self, session: Session, *, series_id: str, video_id: str | None = None,
        event_type: str = "content_published") -> None:
        _enqueue_outbox_event(session, workspace_id=self._workspace_id,
            aggregate_type="video" if video_id is not None else "series", aggregate_id=video_id or series_id,
            event_type=event_type, payload={"series_id": series_id, "video_id": video_id},
            occurred_at=datetime.now(timezone.utc))

    def save_video_knowledge_cards(self, series_id: str, video_id: str, *, title: str, cards: list[KnowledgeCardDTO]) -> None:
        if self.get_video_title(series_id, video_id) is None:
            raise ValueError("Video does not exist.")
        persisted_ids = _persisted_card_ids(cards)
        with self._sessions.begin() as session:
            require_execution_lease(session, self._workspace_id)
            version = session.execute(text("SELECT content_version FROM videos WHERE id=:video FOR UPDATE"), {"video": video_id}).scalar_one()
            session.execute(text("DELETE FROM knowledge_cards WHERE video_id=:video"), {"video": video_id})
            session.execute(text("DELETE FROM knowledge_card_sets WHERE video_id=:video"), {"video": video_id})
            session.execute(text("INSERT INTO knowledge_card_sets (video_id,content_version,title,status,created_at,updated_at) VALUES (:video,:version,:title,'ready',NOW(),NOW())"), {"video": video_id, "version": version, "title": title})
            for ordinal, card in enumerate(cards):
                session.execute(text("INSERT INTO knowledge_cards (id,video_id,ordinal,title,kind,summary,details,tags,keywords,related_card_ids) VALUES (:id,:video,:ordinal,:title,:kind,:summary,:details,CAST(:tags AS JSON),CAST(:keywords AS JSON),CAST(:related AS JSON))"), {"id": persisted_ids[card.id], "video": video_id, "ordinal": ordinal, "title": card.title, "kind": card.kind, "summary": card.summary, "details": card.details, "tags": __import__('json').dumps(card.tags), "keywords": __import__('json').dumps(card.keywords), "related": __import__('json').dumps([persisted_ids[related_id] for related_id in card.related_card_ids if related_id in persisted_ids])})
            _enqueue_outbox_event(
                session,
                workspace_id=self._workspace_id,
                aggregate_type="video_content",
                aggregate_id=video_id,
                event_type="knowledge_cards_published",
                payload={"video_id": video_id},
                occurred_at=datetime.now(timezone.utc),
            )
        self._refresh_rag(series_id, video_id)

    def update_video_summary(self, series_id: str, video_id: str, *, markdown: str) -> VideoSummaryDTO | None:
        current = self._current_payload(series_id, video_id)
        if current is None or current["summary"] is None:
            return None
        parsed = parse_markdown(markdown)
        current["summary"] = {"title": str(parsed.get("title") or current["summary"]["title"]), "markdown": markdown.strip() + "\n", "payload": parsed, "chapters": _chapters_from_summary(parsed)}
        return self._publish_manual_content(series_id, video_id, current, "summary_edit")

    def update_video_transcript(self, series_id: str, video_id: str, *, markdown: str) -> VideoTranscriptDTO | None:
        current = self._current_payload(series_id, video_id)
        if current is None:
            return None
        current["transcript"]["segments"] = [{"start_ms": round(float(item["start_seconds"]) * 1000), "end_ms": round(float(item["end_seconds"]) * 1000), "text": str(item["text"]).strip()} for item in parse_transcript_markdown(markdown)]
        self._publish_manual_content(series_id, video_id, current, "transcript_edit")
        return self.get_video_transcript(series_id, video_id)

    def _publish_manual_content(self, series_id: str, video_id: str, payload: dict[str, Any], operation: str) -> VideoSummaryDTO | None:
        workspace_id = self._workspace_id
        job = self._control.submit_job(workspace_id=workspace_id, resource_type="video", resource_id=video_id, operation=operation, request_payload={"video_id": video_id}, active_key=f"video:{video_id}:{operation}")
        self._content.stage(job_id=job.id, video_id=video_id, payload=payload)
        self._content.publish(job_id=job.id)
        self.clear_generated_artifacts(video_id)
        self._refresh_rag(series_id, video_id)
        return self.get_video_summary(series_id, video_id)

    def publish_generated_content(
        self,
        *,
        series_id: str,
        video_id: str,
        job_id: str,
        worker_id: str,
        lease_token: str,
        payload: dict[str, Any],
    ) -> None:
        """Publish one worker-owned generation result without creating a second job."""

        if self.get_video_title(series_id, video_id) is None:
            raise LookupError(f"video not found '{series_id}/{video_id}'")
        self._content.stage(
            job_id=job_id,
            video_id=video_id,
            payload=payload,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        published = self._content.publish(job_id=job_id, worker_id=worker_id, lease_token=lease_token, finish_job=False)
        observe_video_version(video_id, published.content_version, published=True)
        self.clear_generated_artifacts(video_id)

    def _current_payload(self, series_id: str, video_id: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            source = session.execute(text("""SELECT 1 FROM videos v JOIN series s ON s.id=v.series_id
                WHERE v.id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).scalar()
            transcript = session.execute(text("SELECT language,source_type,duration_ms FROM transcripts WHERE video_id=:video"), {"video": video_id}).mappings().first()
            summary = session.execute(text("SELECT title,markdown,payload,content_format_version FROM summaries WHERE video_id=:video"), {"video": video_id}).mappings().first()
            if source is None or transcript is None:
                return None
            segments = session.execute(text("SELECT start_ms,end_ms,text FROM transcript_segments WHERE video_id=:video ORDER BY ordinal"), {"video": video_id}).mappings().all()
        summary_content = None
        if summary is not None:
            payload = _json_object(summary["payload"])
            summary_content = {"title": summary["title"], "markdown": summary["markdown"], "payload": payload,
                "content_format_version": summary["content_format_version"], "chapters": _chapters_from_summary(payload)}
        return {"transcript": {**dict(transcript), "segments": [dict(row) for row in segments]}, "summary": summary_content}

    def _refresh_rag(self, series_id: str, video_id: str) -> None:
        self._rag_source.refresh_video(workspace_id=self._workspace_id, series_id=series_id, video_id=video_id)

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        with self._sessions() as session:
            row = session.execute(text("""SELECT v.title,m.payload FROM mindmaps m JOIN videos v ON v.id=m.video_id
                JOIN series s ON s.id=v.series_id WHERE m.video_id=:video AND v.series_id=:series AND s.workspace_id=:workspace AND v.deleted_at IS NULL"""), {"video": video_id, "series": series_id, "workspace": self._workspace_id}).mappings().first()
        return None if row is None else VideoMindmapDTO(series_id=series_id, video_id=video_id, title=row["title"], mindmap=_json_object(row["payload"]))

    def get_series_mindmap(self, series_id: str) -> VideoMindmapDTO | None:
        with self._sessions() as session:
            row = session.execute(text("SELECT s.title,m.payload FROM mindmaps m JOIN series s ON s.id=m.series_id WHERE m.series_id=:series AND s.workspace_id=:workspace AND s.deleted_at IS NULL"), {"series": series_id, "workspace": self._workspace_id}).mappings().first()
        return None if row is None else VideoMindmapDTO(series_id=series_id, video_id="", title=row["title"], mindmap=_json_object(row["payload"]))

    def get_series_catalog(self, series_id: str) -> dict[str, object] | None:
        with self._sessions() as session:
            value = session.execute(text("""SELECT c.payload FROM series_catalogs c JOIN series s ON s.id=c.series_id
                WHERE c.series_id=:series AND s.workspace_id=:workspace AND s.deleted_at IS NULL"""), {"series": series_id, "workspace": self._workspace_id}).scalar()
        return None if value is None else _json_object(value)

    def get_rag_documents(self, series_id: str, video_id: str) -> list[dict[str, object]]:
        workspace_id = self._workspace_id
        self._rag_source.refresh_video(workspace_id=workspace_id, series_id=series_id, video_id=video_id)
        with self._sessions() as session:
            rows = session.execute(text("""SELECT c.id,c.text,c.start_ms,c.end_ms,c.note_id,c.card_id,c.metadata,d.source_type,v.title
                FROM rag_chunks c JOIN rag_documents d ON d.id=c.document_id JOIN videos v ON v.id=d.video_id
                JOIN series s ON s.id=v.series_id
                WHERE d.workspace_id=:workspace AND d.series_id=:series AND d.video_id=:video
                AND s.workspace_id=:workspace AND s.deleted_at IS NULL AND v.deleted_at IS NULL
                AND v.content_version=d.source_content_version AND d.state='ready' ORDER BY d.source_type,c.ordinal"""), {"workspace": workspace_id, "series": series_id, "video": video_id}).mappings().all()
        return [{"text": row["text"], "metadata": {**_json_object(row["metadata"]), "doc_id": row["id"], "series_id": series_id, "video_id": video_id, "title": row["title"], "source_type": row["source_type"], "start_seconds": row["start_ms"] / 1000 if row["start_ms"] is not None else None, "end_seconds": row["end_ms"] / 1000 if row["end_ms"] is not None else None, "note_id": row["note_id"] or "", "card_id": row["card_id"] or ""}} for row in rows]


def _chapters_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    chapters = summary.get("chapters", [])
    if not isinstance(chapters, list):
        return []
    result: list[dict[str, Any]] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        start = chapter.get("start_seconds")
        end = chapter.get("end_seconds")
        result.append(
            {
                "title": str(chapter.get("title") or "Untitled"),
                "start_ms": round(float(start) * 1000) if isinstance(start, (int, float)) else None,
                "end_ms": round(float(end) * 1000) if isinstance(end, (int, float)) else None,
                "body": str(chapter.get("summary") or chapter.get("body") or ""),
                "payload": chapter,
            }
        )
    return result


def _clear_deleted_video_content(session: Session, *, video_id: str) -> None:
    """清除软删除视频的遗留内容，使重新导入从未下载状态开始。"""

    for table in (
        "ai_summary_visual_evidence",
        "ai_summaries",
        "notes",
        "mindmaps",
        "knowledge_cards",
        "knowledge_card_sets",
        "summary_chapters",
        "summaries",
        "transcript_segments",
        "transcripts",
        "video_content_state",
        "job_content_staging",
        "external_media_references",
        "media_objects",
        "artifacts",
    ):
        session.execute(text(f"DELETE FROM {table} WHERE video_id=:video"), {"video": video_id})


def _enqueue_outbox_event(
    session: Session,
    *,
    workspace_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> None:
    if not workspace_id.strip():
        raise ValueError("Outbox events require a workspace_id.")
    session.add(
        OutboxEvent(
            id=new_ulid(),
            workspace_id=workspace_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at,
            attempt_count=0,
        )
    )


def _persisted_card_ids(cards: list[KnowledgeCardDTO]) -> dict[str, str]:
    """把模型输出的局部卡片 ID 映射为全局可索引的数据库 ID。"""

    source_ids = [card.id for card in cards]
    if any(not source_id for source_id in source_ids):
        raise ValueError("Generated knowledge cards must include non-empty source IDs.")
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Generated knowledge card source IDs must be unique within a response.")
    return {source_id: new_ulid() for source_id in source_ids}


def _linked_video_from_payload(item: dict[str, object]) -> LinkedVideo:
    source_id = str(item.get("source_id") or item.get("bvid") or "").strip()
    item_index = int(item.get("item_index") or item.get("page") or 1)
    return LinkedVideo(
        source_id=source_id,
        item_index=item_index,
        title=str(item.get("title") or ""),
        cover_url=str(item.get("cover_url") or ""),
        duration_seconds=int(item.get("duration_seconds") or 0),
        source_url=str(item.get("source_url") or ""),
        provider=str(item.get("provider") or "bilibili"),
        download_key=str(item.get("download_key") or ""),
    )


def _linked_video_sources(payload: object) -> dict[str, LinkedVideo]:
    if payload is None:
        return {}
    sources = [_linked_video_from_payload(item) for item in _json_object(payload).get("videos", [])]
    return {source.video_id: source for source in sources}


def _json_object(value: object) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise ValueError("Expected a JSON object in the SQL content store.")
    return decoded


def _json_list(value: object) -> list[str]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise ValueError("Expected a JSON string array in the SQL content store.")
    return decoded


def _json_list_of_objects(value: object) -> list[dict[str, Any]]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, list) or not all(isinstance(item, dict) for item in decoded):
        raise ValueError("Expected a JSON object array in the SQL content store.")
    return decoded


def _attach_chapter_transcript(
    summary: dict[str, Any],
    transcript_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Restore per-chapter transcript expansion from current SQL transcript rows."""

    chapters = summary.get("chapters")
    if not isinstance(chapters, list):
        return summary

    assigned_segments: list[list[dict[str, Any]]] = [[] for _ in chapters]
    ranges = [
        (_as_optional_seconds(chapter.get("start_seconds")), _as_optional_seconds(chapter.get("end_seconds")))
        if isinstance(chapter, dict) else (None, None)
        for chapter in chapters
    ]
    for segment in transcript_segments:
        for index, (start, end) in enumerate(ranges):
            if start is not None and end is not None and start <= segment["start_seconds"] < end:
                assigned_segments[index].append(segment)
                break

    enriched_chapters: list[object] = []
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            enriched_chapters.append(chapter)
            continue
        enriched_chapters.append({**chapter, "transcript_segments": assigned_segments[index]})
    return {**summary, "chapters": enriched_chapters}


def _attach_chapter_image_urls(
    summary: dict[str, Any],
    *,
    series_id: str,
    video_id: str,
) -> dict[str, Any]:
    """为已生成的章节截图补齐前端可直接读取的 API 地址。"""

    chapters = summary.get("chapters")
    if not isinstance(chapters, list):
        return summary

    enriched_chapters: list[object] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            enriched_chapters.append(chapter)
            continue
        image_filename = chapter.get("image_filename")
        if (
            not isinstance(image_filename, str)
            or Path(image_filename).name != image_filename
            or Path(image_filename).suffix.lower() != ".jpg"
        ):
            enriched_chapters.append(chapter)
            continue
        enriched_chapters.append(
            {
                **chapter,
                "image_url": (
                    f"/api/videos/{quote(series_id, safe='')}/{quote(video_id, safe='')}"
                    f"/screenshots/{quote(image_filename, safe='')}"
                ),
            }
        )
    return {**summary, "chapters": enriched_chapters}


def _as_optional_seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()
