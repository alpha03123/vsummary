"""将旧 ``videos/`` 与 ``workspace/`` 一次性导入 MySQL/BlobStore。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.video_summary.infrastructure.persistence.blob_store import BlobReference, BlobStoreError, FileBlobStore
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.current_content_repository import SqlCurrentContentRepository
from backend.video_summary.infrastructure.persistence.ids import new_ulid
from backend.video_summary.infrastructure.persistence.models import LegacyImportItem, MediaObject
from backend.video_summary.infrastructure.persistence.sql_rag_source import SqlRagSourceRepository


MEDIA_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
LEGACY_IMPORT_FORMAT_VERSION = 4


@dataclass(frozen=True)
class LegacyImportReport:
    series_imported: int
    videos_imported: int
    content_imported: int
    failures: tuple[str, ...]


class LegacyWorkspaceImporter:
    """显式迁移工具；它不会被正常 API 启动路径自动调用。"""

    def __init__(self, *, root_dir: Path, session_factory: sessionmaker[Session], blob_store: FileBlobStore) -> None:
        self._root_dir = root_dir
        self._session_factory = session_factory
        self._blob_store = blob_store
        self._control = SqlControlPlaneRepository(session_factory)
        self._content = SqlCurrentContentRepository(session_factory)
        self._rag_source = SqlRagSourceRepository(session_factory)

    def import_local_workspace(self) -> LegacyImportReport:
        if self.is_completed():
            return LegacyImportReport(0, 0, 0, ())
        workspace_id = self._workspace_id()
        imported_series = imported_videos = imported_content = 0
        failures: list[str] = []
        linked_root = self._root_dir / "workspace"
        if linked_root.is_dir():
            for directory in sorted(path for path in linked_root.iterdir() if path.is_dir()):
                metadata = directory / "linked_series.json"
                if metadata.is_file():
                    try:
                        self._import_linked_series(workspace_id, directory.name, metadata)
                    except Exception as error:
                        failures.append(f"{directory.name}: {error}")
        try:
            self._import_agent_sessions()
            self._import_llm_usage()
        except Exception as error:
            failures.append(f"agent state: {error}")
        videos_root = self._root_dir / "videos"
        if videos_root.is_dir():
            for position, series_dir in enumerate(sorted(path for path in videos_root.iterdir() if path.is_dir())):
                try:
                    series_id, created = self._series_id(workspace_id, series_dir, position)
                    imported_series += int(created)
                    for media_path in sorted(path for path in series_dir.iterdir() if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES):
                        video_id, created_video = self._video_id(series_id, series_dir.name, media_path)
                        imported_videos += int(created_video)
                        self._import_media(video_id, media_path)
                        if self._import_content(workspace_id, video_id, series_dir.name, media_path.stem):
                            imported_content += 1
                        self._import_structured_artifacts(video_id, series_dir.name, media_path.stem)
                        self._import_binary_artifacts(workspace_id, video_id, series_dir.name, media_path.stem)
                        self._rag_source.refresh_video(workspace_id=workspace_id, series_id=series_id, video_id=video_id)
                except Exception as error:
                    failures.append(f"{series_dir.name}: {error}")
        self._repair_titles_from_linked_metadata()
        if not failures:
            self._mark_completed()
        return LegacyImportReport(imported_series, imported_videos, imported_content, tuple(failures))

    def _import_agent_sessions(self) -> None:
        directory = self._root_dir / "data" / "agent_sessions"
        if not directory.is_dir():
            return
        for path in directory.glob("*.json"):
            key = f"agent_session/{path.name}"
            if self._mapped("agent_session", key) is not None:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            session_id = str(payload.get("session_id") or "")
            memory_key = str(payload.get("memory_key") or "")
            if not session_id or not memory_key:
                raise ValueError(f"invalid legacy agent session: {path.name}")
            with self._session_factory.begin() as session:
                session.execute(__import__("sqlalchemy").text("INSERT INTO agent_session_snapshots (session_id,memory_key,payload,updated_at) VALUES (:id,:key,CAST(:payload AS JSON),NOW()) ON DUPLICATE KEY UPDATE memory_key=VALUES(memory_key),payload=VALUES(payload),updated_at=NOW()"), {"id": session_id, "key": memory_key, "payload": json.dumps(payload, ensure_ascii=False)})
            self._record("agent_session", key, "agent_session", session_id[:26], "imported", _sha256(path))

    def _import_llm_usage(self) -> None:
        path = self._root_dir / "data" / "usage" / "llm_usage.sqlite3"
        key = "llm_usage/sqlite"
        if not path.is_file() or self._mapped("llm_usage", key) is not None:
            return
        connection = sqlite3.connect(path)
        try:
            rows = connection.execute("SELECT created_at,category,provider,base_url,model,prompt_tokens,completion_tokens,total_tokens FROM llm_usage").fetchall()
        finally:
            connection.close()
        with self._session_factory.begin() as session:
            for row in rows:
                session.execute(__import__("sqlalchemy").text("INSERT INTO llm_usage (id,created_at,category,provider,base_url,model,prompt_tokens,completion_tokens,total_tokens) VALUES (:id,:created,:category,:provider,:base,:model,:prompt,:completion,:total)"), {"id": new_ulid(), "created": row[0], "category": row[1], "provider": row[2], "base": row[3], "model": row[4], "prompt": row[5], "completion": row[6], "total": row[7]})
        self._record("llm_usage", key, "llm_usage", "", "imported", _sha256(path))

    def is_completed(self) -> bool:
        with self._session_factory() as session:
            row = session.execute(__import__("sqlalchemy").text("SELECT data_format_version,legacy_import_state FROM app_installations ORDER BY created_at LIMIT 1")).first()
        return row is not None and row[1] == "completed" and row[0] >= LEGACY_IMPORT_FORMAT_VERSION

    def _mark_completed(self) -> None:
        with self._session_factory.begin() as session:
            installation_id = session.execute(__import__("sqlalchemy").text("SELECT id FROM app_installations ORDER BY created_at LIMIT 1 FOR UPDATE")).scalar()
            if installation_id is None:
                session.execute(__import__("sqlalchemy").text("INSERT INTO app_installations (id,data_format_version,legacy_import_state,created_at,updated_at) VALUES (:id,:version,'completed',NOW(),NOW())"), {"id": new_ulid(), "version": LEGACY_IMPORT_FORMAT_VERSION})
            else:
                session.execute(__import__("sqlalchemy").text("UPDATE app_installations SET data_format_version=:version,legacy_import_state='completed',legacy_import_error=NULL,updated_at=NOW() WHERE id=:id"), {"id": installation_id, "version": LEGACY_IMPORT_FORMAT_VERSION})

    def _import_linked_series(self, workspace_id: str, legacy_series_id: str, metadata_path: Path) -> None:
        source_key = f"linked/{legacy_series_id}"
        if self._mapped("linked_series", source_key) is not None:
            return
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        existing_series = self._mapped("series", legacy_series_id)
        if existing_series is not None and existing_series.target_id:
            series_id = existing_series.target_id
            with self._session_factory.begin() as session:
                session.execute(__import__("sqlalchemy").text("UPDATE series SET title=:title,source_kind='linked',external_source_url=:url,updated_at=NOW() WHERE id=:series"), {"series": series_id, "title": str(payload.get("title") or legacy_series_id), "url": str(payload.get("source_url") or "")})
        else:
            with self._session_factory() as session:
                position = int(session.execute(__import__("sqlalchemy").text("SELECT COALESCE(MAX(position),-1)+1 FROM series WHERE workspace_id=:workspace"), {"workspace": workspace_id}).scalar_one())
            series_id = self._control.create_series(workspace_id=workspace_id, title=str(payload.get("title") or legacy_series_id), position=position, source_kind="linked", external_source_url=str(payload.get("source_url") or ""))
            self._record("series", legacy_series_id, "series", series_id, "imported")
        with self._session_factory.begin() as session:
            session.execute(__import__("sqlalchemy").text("INSERT INTO linked_series_metadata (series_id,payload,created_at,updated_at) VALUES (:series,CAST(:payload AS JSON),NOW(),NOW())"), {"series": series_id, "payload": json.dumps(payload, ensure_ascii=False)})
        for item in payload.get("videos", []):
            if not isinstance(item, dict):
                continue
            source_id = _linked_source_id(item)
            index = int(item.get("item_index") or item.get("page") or 1)
            external_id = source_id if index == 1 else f"{source_id}_p{index}"
            if not external_id:
                continue
            with self._session_factory() as session:
                existing_video = session.execute(__import__("sqlalchemy").text("SELECT id FROM videos WHERE series_id=:series AND external_source_id=:external"), {"series": series_id, "external": external_id}).scalar()
            if existing_video is None:
                self._control.create_video(series_id=series_id, title=str(item.get("title") or external_id), source_kind=str(item.get("provider") or "linked"), external_source_id=external_id, duration_ms=round(float(item.get("duration_seconds") or 0) * 1000))
        self._record("linked_series", source_key, "series", series_id, "imported", _sha256(metadata_path))

    def _workspace_id(self) -> str:
        key = str(self._root_dir.resolve())
        item = self._mapped("workspace", key)
        if item is not None and item.target_id:
            return item.target_id
        workspace_id = self._control.create_workspace(owner_scope_id="legacy-local", title="Migrated local library")
        self._record("workspace", key, "workspace", workspace_id, "imported")
        return workspace_id

    def _series_id(self, workspace_id: str, series_dir: Path, position: int) -> tuple[str, bool]:
        key = series_dir.name
        item = self._mapped("series", key)
        if item is not None and item.target_id:
            return item.target_id, False
        title = _legacy_title(self._root_dir / "workspace" / key / "series_meta.json", fallback=key)
        with self._session_factory() as session:
            existing_series_id = session.execute(
                __import__("sqlalchemy").text(
                    "SELECT id FROM series WHERE workspace_id=:workspace AND title=:title AND deleted_at IS NULL"
                ),
                {"workspace": workspace_id, "title": title},
            ).scalar()
            position_taken = session.execute(
                __import__("sqlalchemy").text(
                    "SELECT 1 FROM series WHERE workspace_id=:workspace AND position=:position AND deleted_at IS NULL"
                ),
                {"workspace": workspace_id, "position": position},
            ).scalar() is not None
            next_position = int(
                session.execute(
                    __import__("sqlalchemy").text(
                        "SELECT COALESCE(MAX(position), -1) + 1 FROM series WHERE workspace_id=:workspace AND deleted_at IS NULL"
                    ),
                    {"workspace": workspace_id},
                ).scalar_one()
            )
        if existing_series_id is not None:
            self._record("series", key, "series", existing_series_id, "imported")
            return existing_series_id, False
        series_id = self._control.create_series(
            workspace_id=workspace_id,
            title=title,
            position=next_position if position_taken else position,
        )
        self._record("series", key, "series", series_id, "imported")
        return series_id, True

    def _video_id(self, series_id: str, legacy_series_id: str, media_path: Path) -> tuple[str, bool]:
        key = f"{legacy_series_id}/{media_path.name}"
        item = self._mapped("video", key)
        if item is not None and item.target_id:
            return item.target_id, False
        title = _legacy_title(self._root_dir / "workspace" / legacy_series_id / media_path.stem / "video_meta.json", fallback=media_path.stem)
        with self._session_factory() as session:
            existing_video = session.execute(__import__("sqlalchemy").text("SELECT id FROM videos WHERE series_id=:series AND external_source_id=:external"), {"series": series_id, "external": media_path.stem}).scalar()
        if existing_video is not None:
            self._record("video", key, "video", existing_video, "imported", _sha256(media_path))
            return existing_video, False
        video_id = self._control.create_video(series_id=series_id, title=title, source_kind="local", external_source_id=media_path.stem)
        self._record("video", key, "video", video_id, "imported", _sha256(media_path))
        return video_id, True

    def _import_media(self, video_id: str, media_path: Path) -> None:
        key = f"media/{video_id}/source{media_path.suffix.lower()}"
        with self._session_factory() as session:
            existing = session.scalar(select(MediaObject).where(MediaObject.video_id == video_id))
            if existing is not None:
                reference = BlobReference(
                    key=existing.blob_key,
                    sha256=existing.sha256,
                    byte_size=existing.byte_size,
                    content_type=existing.media_type,
                )
                try:
                    self._blob_store.stat(reference)
                    return
                except BlobStoreError:
                    pass
        with media_path.open("rb") as source:
            staged = self._blob_store.put_staging(job_id=f"legacy{video_id}", source=source, content_type="application/octet-stream")
        reference = self._blob_store.commit(staged, object_key=key)
        with self._session_factory.begin() as session:
            if existing is None:
                session.add(MediaObject(id=new_ulid(), video_id=video_id, blob_key=reference.key, media_type=reference.content_type, byte_size=reference.byte_size, sha256=reference.sha256, state="ready"))
            else:
                session.execute(
                    __import__("sqlalchemy").text(
                        "UPDATE media_objects SET blob_key=:key,media_type=:type,byte_size=:size,sha256=:sha,state='ready',updated_at=NOW() WHERE id=:id"
                    ),
                    {"id": existing.id, "key": reference.key, "type": reference.content_type, "size": reference.byte_size, "sha": reference.sha256},
                )

    def _repair_titles_from_linked_metadata(self) -> None:
        """从旧链接元数据恢复被文件名退化覆盖的平台视频标题。"""

        with self._session_factory.begin() as session:
            rows = session.execute(
                __import__("sqlalchemy").text("""SELECT v.id,v.title,v.external_source_id,m.payload
                    FROM videos v JOIN linked_series_metadata m ON m.series_id=v.series_id
                    WHERE v.deleted_at IS NULL AND v.external_source_id IS NOT NULL""")
            ).mappings().all()
            for row in rows:
                payload = row["payload"]
                decoded = json.loads(payload) if isinstance(payload, str) else payload
                if not isinstance(decoded, dict):
                    continue
                metadata = next(
                    (
                        item
                        for item in decoded.get("videos", [])
                        if isinstance(item, dict) and _linked_video_id(item) == row["external_source_id"]
                    ),
                    None,
                )
                if metadata is None:
                    continue
                title = str(metadata.get("title") or "").strip()
                if not title or row["title"] not in {row["external_source_id"], _linked_source_id(metadata)}:
                    continue
                session.execute(
                    __import__("sqlalchemy").text("UPDATE videos SET title=:title,row_version=row_version+1,updated_at=NOW() WHERE id=:id"),
                    {"id": row["id"], "title": title},
                )

    def _import_content(self, workspace_id: str, video_id: str, legacy_series_id: str, legacy_video_id: str) -> bool:
        base = self._root_dir / "workspace" / legacy_series_id / legacy_video_id
        transcript_path, summary_path = base / "transcript.cleaned.json", base / "summary.json"
        if not transcript_path.is_file() or not summary_path.is_file():
            return False
        key = f"content/{legacy_series_id}/{legacy_video_id}"
        item = self._mapped("content", key)
        if item is not None and item.status == "imported":
            return False
        transcript, summary = json.loads(transcript_path.read_text(encoding="utf-8")), json.loads(summary_path.read_text(encoding="utf-8"))
        payload = _to_current_content(transcript, summary)
        job = self._control.submit_job(workspace_id=workspace_id, resource_type="video", resource_id=video_id, operation="legacy_import", request_payload={"source": key}, active_key=f"legacy:{video_id}")
        self._content.stage(job_id=job.id, video_id=video_id, payload=payload)
        self._content.publish(job_id=job.id)
        self._record("content", key, "video_content", video_id, "imported", _sha256(summary_path))
        return True

    def _import_structured_artifacts(self, video_id: str, legacy_series_id: str, legacy_video_id: str) -> None:
        base = self._root_dir / "workspace" / legacy_series_id / legacy_video_id
        for filename, kind, target in (
            ("notes.json", "notes", "notes"),
            ("knowledge_cards.json", "knowledge_cards", "knowledge_cards"),
            ("mindmap.json", "mindmap", "mindmaps"),
            ("ai_summary.json", "ai_summary", "ai_summaries"),
            ("ai_summary.visual_evidence.json", "ai_summary_evidence", "ai_summary_visual_evidence"),
        ):
            path = base / filename
            if not path.is_file() or self._mapped(kind, f"{legacy_series_id}/{legacy_video_id}") is not None:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            with self._session_factory.begin() as session:
                if target == "notes":
                    for note in payload.get("notes", []):
                        if isinstance(note, dict):
                            session.execute(__import__("sqlalchemy").text("INSERT INTO notes (id, video_id, title, content, source, row_version, created_at, updated_at) VALUES (:id,:video,:title,:content,:source,1,NOW(),NOW())"), {"id": str(note.get("id") or new_ulid())[:26], "video": video_id, "title": str(note.get("title") or "Untitled"), "content": str(note.get("content") or ""), "source": str(note.get("source") or "manual")})
                elif target == "knowledge_cards":
                    session.execute(__import__("sqlalchemy").text("INSERT INTO knowledge_card_sets (video_id, content_version, title, status, created_at, updated_at) VALUES (:video,1,:title,'ready',NOW(),NOW())"), {"video": video_id, "title": str(payload.get("title") or "")})
                    for ordinal, card in enumerate(payload.get("cards", [])):
                        if isinstance(card, dict):
                            session.execute(__import__("sqlalchemy").text("INSERT INTO knowledge_cards (id,video_id,ordinal,title,kind,summary,details,tags,keywords,related_card_ids) VALUES (:id,:video,:ordinal,:title,:kind,:summary,:details,CAST(:tags AS JSON),CAST(:keywords AS JSON),CAST(:related AS JSON))"), {"id": str(card.get("id") or new_ulid())[:26], "video": video_id, "ordinal": ordinal, "title": str(card.get("title") or "Untitled"), "kind": str(card.get("kind") or "concept"), "summary": str(card.get("summary") or ""), "details": str(card.get("details") or ""), "tags": json.dumps(card.get("tags") or []), "keywords": json.dumps(card.get("keywords") or []), "related": json.dumps(card.get("related_card_ids") or [])})
                elif target == "mindmaps":
                    session.execute(__import__("sqlalchemy").text("INSERT INTO mindmaps (id,video_id,content_version,title,payload,row_version,created_at,updated_at) VALUES (:id,:video,1,:title,CAST(:payload AS JSON),1,NOW(),NOW())"), {"id": new_ulid(), "video": video_id, "title": legacy_video_id, "payload": json.dumps(payload, ensure_ascii=False)})
                elif target == "ai_summaries":
                    session.execute(__import__("sqlalchemy").text("INSERT INTO ai_summaries (video_id,title,content,citations,status,created_at,updated_at) VALUES (:video,:title,:content,CAST(:citations AS JSON),'ready',NOW(),NOW())"), {"video": video_id, "title": str(payload.get("title") or "Untitled"), "content": str(payload.get("content") or ""), "citations": json.dumps(payload.get("citations") or [])})
                else:
                    for ordinal, frame in enumerate(payload.get("frames", [])):
                        if isinstance(frame, dict):
                            session.execute(__import__("sqlalchemy").text("INSERT INTO ai_summary_visual_evidence (id,video_id,ordinal,timestamp_ms,text) VALUES (:id,:video,:ordinal,:timestamp,:text)"), {"id": new_ulid(), "video": video_id, "ordinal": ordinal, "timestamp": round(float(frame.get("timestamp_seconds") or 0)*1000), "text": str(frame.get("text") or "")})
            self._record(kind, f"{legacy_series_id}/{legacy_video_id}", target, video_id, "imported", _sha256(path))

    def _import_binary_artifacts(self, workspace_id: str, video_id: str, legacy_series_id: str, legacy_video_id: str) -> None:
        base = self._root_dir / "workspace" / legacy_series_id / legacy_video_id
        for directory_name, kind in (("screenshots", "screenshot"), ("frames", "note_frame")):
            directory = base / directory_name
            if not directory.is_dir():
                continue
            for source in directory.glob("*.jpg"):
                source_key = f"{kind}/{legacy_series_id}/{legacy_video_id}/{source.name}"
                if self._mapped("binary_artifact", source_key) is not None:
                    continue
                with source.open("rb") as stream:
                    staged = self._blob_store.put_staging(job_id=f"legacy{video_id}", source=stream, content_type="image/jpeg")
                reference = self._blob_store.commit(staged, object_key=f"artifacts/{video_id}/{kind}/{source.name}")
                with self._session_factory.begin() as session:
                    session.execute(__import__("sqlalchemy").text("INSERT INTO artifacts (id,workspace_id,video_id,content_version,kind,blob_key,sha256,byte_size,media_type,created_at,updated_at) VALUES (:id,:workspace,:video,1,:kind,:key,:sha,:size,:type,NOW(),NOW())"), {"id": new_ulid(), "workspace": workspace_id, "video": video_id, "kind": kind, "key": reference.key, "sha": reference.sha256, "size": reference.byte_size, "type": reference.content_type})
                self._record("binary_artifact", source_key, "artifact", video_id, "imported", reference.sha256)

    def _mapped(self, source_kind: str, source_key: str) -> LegacyImportItem | None:
        with self._session_factory() as session:
            return session.scalar(select(LegacyImportItem).where(LegacyImportItem.source_kind == source_kind, LegacyImportItem.source_key == source_key))

    def _record(self, source_kind: str, source_key: str, target_type: str, target_id: str, status: str, checksum: str | None = None) -> None:
        with self._session_factory.begin() as session:
            existing = session.scalar(select(LegacyImportItem).where(LegacyImportItem.source_kind == source_kind, LegacyImportItem.source_key == source_key).with_for_update())
            if existing is None:
                session.add(LegacyImportItem(id=new_ulid(), source_kind=source_kind, source_key=source_key, target_type=target_type, target_id=target_id, source_sha256=checksum, status=status))


def _legacy_title(path: Path, *, fallback: str) -> str:
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        title = payload.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return fallback


def _linked_source_id(item: dict[str, object]) -> str:
    return str(item.get("source_id") or item.get("bvid") or "").strip()


def _linked_video_id(item: dict[str, object]) -> str:
    source_id = _linked_source_id(item)
    index = int(item.get("item_index") or item.get("page") or 1)
    return source_id if index == 1 else f"{source_id}_p{index}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _to_current_content(transcript: dict[str, object], summary: dict[str, object]) -> dict[str, object]:
    segments = [{"start_ms": round(float(item["start_seconds"]) * 1000), "end_ms": round(float(item["end_seconds"]) * 1000), "text": str(item["text"])} for item in transcript.get("segments", []) if isinstance(item, dict)]
    chapters = [{"title": str(item.get("title", "Untitled")), "start_ms": round(float(item["start_seconds"]) * 1000) if item.get("start_seconds") is not None else None, "end_ms": round(float(item["end_seconds"]) * 1000) if item.get("end_seconds") is not None else None, "body": str(item.get("summary", "")), "payload": item} for item in summary.get("chapters", []) if isinstance(item, dict)]
    return {"transcript": {"language": str(transcript.get("language") or "und"), "source_type": "legacy", "duration_ms": round(float(transcript.get("duration_seconds") or 0) * 1000), "segments": segments}, "summary": {"title": str(summary.get("title") or "Untitled"), "markdown": "", "payload": summary, "chapters": chapters}}
