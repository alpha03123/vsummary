from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.shared.filesystem import KeyedLockManager, atomic_write_text
from backend.agent.memory.context import AgentContext
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.session.models import AgentSessionMessageEntry, AgentSessionSnapshot, utc_now_iso


class FileAgentSessionStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._session_locks = KeyedLockManager()

    def get_snapshot(self, session_id: str) -> AgentSessionSnapshot | None:
        with self._session_locks.hold(session_id):
            return self._read_snapshot_unlocked(session_id)

    def append_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        messages: list[AgentChatMessage],
    ) -> None:
        with self._session_locks.hold(session_id):
            snapshot = self._read_snapshot_unlocked(session_id)
            timestamp = utc_now_iso()
            sanitized_context = context.model_copy()
            if snapshot is None:
                snapshot = AgentSessionSnapshot(
                    session_id=session_id,
                    memory_key=memory_key,
                    context=sanitized_context,
                    updated_at=timestamp,
                )

            snapshot.context = sanitized_context
            snapshot.memory_key = memory_key
            snapshot.messages = [
                AgentSessionMessageEntry(role=message.role, content=message.content, created_at=timestamp)
                for message in messages
            ]
            snapshot.updated_at = timestamp
            self._write_snapshot(snapshot)

    def clear_snapshot(self, session_id: str) -> None:
        with self._session_locks.hold(session_id):
            snapshot_path = self._build_snapshot_path(session_id)
            if snapshot_path.exists():
                snapshot_path.unlink()

    def _write_snapshot(self, snapshot: AgentSessionSnapshot) -> None:
        snapshot_path = self._build_snapshot_path(snapshot.session_id)
        atomic_write_text(
            snapshot_path,
            snapshot.model_dump_json(indent=2),
        )

    def _read_snapshot_unlocked(self, session_id: str) -> AgentSessionSnapshot | None:
        snapshot_path = self._build_snapshot_path(session_id)
        if not snapshot_path.exists():
            return None
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        return AgentSessionSnapshot.model_validate(payload)

    def _build_snapshot_path(self, session_id: str) -> Path:
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()
        return self._root_dir / f"{digest}.json"
