"""从 MySQL 当前内容构建可重建的 RAG source chunks。"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from backend.core.ids import new_ulid


class SqlRagSourceRepository:
    """RAG 文本源的唯一权威实现，不扫描 workspace 文件或 signature 文件。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def refresh_video(self, *, workspace_id: str, series_id: str, video_id: str) -> int:
        with self._sessions.begin() as session:
            version = session.execute(text("SELECT content_version FROM videos WHERE id=:video AND series_id=:series AND deleted_at IS NULL FOR UPDATE"), {"video": video_id, "series": series_id}).scalar()
            if version is None:
                return 0
            documents = _video_documents(session, video_id)
            for source_type, chunks in documents.items():
                document_id = session.execute(text("SELECT id FROM rag_documents WHERE video_id=:video AND source_type=:kind FOR UPDATE"), {"video": video_id, "kind": source_type}).scalar()
                content_hash = _hash("\n".join(chunk["text"] for chunk in chunks))
                if document_id is None:
                    document_id = new_ulid()
                    session.execute(text("INSERT INTO rag_documents (id,workspace_id,series_id,video_id,source_content_version,source_type,content_hash,state,created_at,updated_at) VALUES (:id,:workspace,:series,:video,:version,:kind,:hash,'ready',NOW(),NOW())"), {"id": document_id, "workspace": workspace_id, "series": series_id, "video": video_id, "version": version, "kind": source_type, "hash": content_hash})
                else:
                    session.execute(text("UPDATE rag_documents SET source_content_version=:version,content_hash=:hash,state='ready',updated_at=NOW() WHERE id=:id"), {"id": document_id, "version": version, "hash": content_hash})
                    session.execute(text("DELETE FROM rag_chunks WHERE document_id=:id"), {"id": document_id})
                for ordinal, chunk in enumerate(chunks):
                    session.execute(text("INSERT INTO rag_chunks (id,document_id,source_content_version,ordinal,text,text_hash,start_ms,end_ms,chapter_id,note_id,card_id,metadata) VALUES (:id,:document,:version,:ordinal,:text,:hash,:start,:end,:chapter,:note,:card,CAST(:metadata AS JSON))"), {"id": new_ulid(), "document": document_id, "version": version, "ordinal": ordinal, "text": chunk["text"], "hash": _hash(chunk["text"]), "start": chunk.get("start_ms"), "end": chunk.get("end_ms"), "chapter": None, "note": chunk.get("note_id"), "card": chunk.get("card_id"), "metadata": json.dumps(chunk.get("metadata", {}), ensure_ascii=False)})
            return sum(len(chunks) for chunks in documents.values())

    def current_chunks(self, *, workspace_id: str, series_id: str) -> list[dict[str, object]]:
        with self._sessions() as session:
            rows = session.execute(text("""SELECT c.id,c.text,c.start_ms,c.end_ms,c.metadata,d.video_id,d.source_type,v.title
                FROM rag_chunks c JOIN rag_documents d ON d.id=c.document_id JOIN videos v ON v.id=d.video_id
                WHERE d.workspace_id=:workspace AND d.series_id=:series AND d.state='ready' AND v.content_version=d.source_content_version AND v.deleted_at IS NULL ORDER BY d.video_id,c.ordinal"""), {"workspace": workspace_id, "series": series_id}).mappings().all()
        return [{**dict(row), "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]} for row in rows]


def _video_documents(session: Session, video_id: str) -> dict[str, list[dict[str, object]]]:
    documents: dict[str, list[dict[str, object]]] = {}
    summary = session.execute(text("SELECT title,markdown,payload FROM summaries WHERE video_id=:video"), {"video": video_id}).mappings().first()
    if summary is not None:
        payload = json.loads(summary["payload"]) if isinstance(summary["payload"], str) else summary["payload"]
        documents["summary"] = [{"text": summary["markdown"] or json.dumps(payload, ensure_ascii=False), "metadata": {"source_family": "summary", "title": summary["title"]}}]
    segments = session.execute(text("SELECT start_ms,end_ms,text FROM transcript_segments WHERE video_id=:video ORDER BY ordinal"), {"video": video_id}).mappings().all()
    if segments:
        documents["transcript"] = [{"text": row["text"], "start_ms": row["start_ms"], "end_ms": row["end_ms"], "metadata": {"source_family": "transcript"}} for row in segments]
    notes = session.execute(text("SELECT id,title,content FROM notes WHERE video_id=:video AND deleted_at IS NULL"), {"video": video_id}).mappings().all()
    if notes:
        documents["notes"] = [{"text": f"{row['title']}\n{row['content']}", "note_id": row["id"], "metadata": {"source_family": "notes"}} for row in notes]
    cards = session.execute(text("SELECT id,title,summary,details FROM knowledge_cards WHERE video_id=:video ORDER BY ordinal"), {"video": video_id}).mappings().all()
    if cards:
        documents["cards"] = [{"text": f"{row['title']}\n{row['summary']}\n{row['details']}", "card_id": row["id"], "metadata": {"source_family": "cards"}} for row in cards]
    return documents


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
