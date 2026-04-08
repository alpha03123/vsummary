from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.tool_calls import ToolExecutionResult
from backend.agent.session.evidence_cache import build_cache_entries
from backend.agent.session.models import AgentSessionMessageEntry, AgentSessionSnapshot, utc_now_iso


class AgentSessionStore(Protocol):
    def get_snapshot(self, session_id: str) -> AgentSessionSnapshot | None:
        ...

    def append_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        user_message: str,
        assistant_message: str,
        tool_results: list[ToolExecutionResult],
    ) -> None:
        ...

    def clear_snapshot(self, session_id: str) -> None:
        ...


class FileAgentSessionStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def get_snapshot(self, session_id: str) -> AgentSessionSnapshot | None:
        snapshot_path = self._build_snapshot_path(session_id)
        if not snapshot_path.exists():
            return None
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        return AgentSessionSnapshot.model_validate(payload)

    def append_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        user_message: str,
        assistant_message: str,
        tool_results: list[ToolExecutionResult],
    ) -> None:
        snapshot = self.get_snapshot(session_id)
        timestamp = utc_now_iso()
        sanitized_context = context.model_copy(update={"recent_messages": []})
        if snapshot is None:
            snapshot = AgentSessionSnapshot(
                session_id=session_id,
                memory_key=memory_key,
                context=sanitized_context,
                updated_at=timestamp,
            )

        snapshot.context = sanitized_context
        snapshot.memory_key = memory_key
        snapshot.messages.extend(
            [
                AgentSessionMessageEntry(role="user", content=user_message, created_at=timestamp),
                AgentSessionMessageEntry(role="assistant", content=assistant_message, created_at=timestamp),
            ]
        )
        snapshot.evidence_entries = build_cache_entries(
            snapshot.evidence_entries,
            tool_results,
            updated_at=timestamp,
        )
        snapshot.updated_at = timestamp
        self._write_snapshot(snapshot)

    def clear_snapshot(self, session_id: str) -> None:
        snapshot_path = self._build_snapshot_path(session_id)
        if snapshot_path.exists():
            snapshot_path.unlink()

    def _write_snapshot(self, snapshot: AgentSessionSnapshot) -> None:
        snapshot_path = self._build_snapshot_path(snapshot.session_id)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            snapshot.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _build_snapshot_path(self, session_id: str) -> Path:
        digest = hashlib.sha1(session_id.encode("utf-8")).hexdigest()
        return self._root_dir / f"{digest}.json"
