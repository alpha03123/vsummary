"""MySQL Agent 会话快照存储。"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.session.models import AgentSessionMessageEntry, AgentSessionSnapshot


class SqlAgentSessionStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def get_snapshot(self, session_id: str) -> AgentSessionSnapshot | None:
        with self._sessions() as session:
            payload = session.execute(text("SELECT payload FROM agent_session_snapshots WHERE session_id=:id"), {"id": session_id}).scalar()
        if payload is None:
            return None
        return AgentSessionSnapshot.model_validate(json.loads(payload) if isinstance(payload, str) else payload)

    def append_turn(self, *, session_id: str, memory_key: str, context: AgentContext, messages: list[AgentChatMessage]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        snapshot = AgentSessionSnapshot(session_id=session_id, memory_key=memory_key, context=context.model_copy(), messages=[AgentSessionMessageEntry(role=item.role, content=item.content, created_at=timestamp, citations=item.citations) for item in messages], updated_at=timestamp)
        with self._sessions.begin() as session:
            session.execute(text("""INSERT INTO agent_session_snapshots (session_id,memory_key,payload,updated_at) VALUES (:id,:key,CAST(:payload AS JSON),NOW())
                ON DUPLICATE KEY UPDATE memory_key=VALUES(memory_key),payload=VALUES(payload),updated_at=NOW()"""), {"id": session_id, "key": memory_key, "payload": snapshot.model_dump_json()})

    def clear_snapshot(self, session_id: str) -> None:
        with self._sessions.begin() as session:
            session.execute(text("DELETE FROM agent_session_snapshots WHERE session_id=:id"), {"id": session_id})
