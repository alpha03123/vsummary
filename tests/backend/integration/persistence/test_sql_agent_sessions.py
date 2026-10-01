from __future__ import annotations

import pytest

from backend.agent.memory.context import AgentContext
from backend.core.chat import ChatMessage
from backend.core.ids import new_ulid
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.sql_agent_session_store import SqlAgentSessionStore


def test_reads_updates_and_clears_only_the_bound_workspace(mysql_sessions) -> None:
    control = SqlControlPlaneRepository(mysql_sessions)
    stores = [
        SqlAgentSessionStore(
            mysql_sessions,
            workspace_id=control.create_workspace(owner_scope_id=f"test-{new_ulid()}", title=title),
        )
        for title in ("Workspace A", "Workspace B")
    ]
    session_id = new_ulid()
    for store, content in zip(stores, ("A original", "B original")):
        store.append_turn(
            session_id=session_id, memory_key=session_id,
            context=AgentContext(session_id=session_id),
            messages=[ChatMessage(role="user", content=content)],
        )
    assert stores[0].get_snapshot(session_id).messages[0].content == "A original"
    assert stores[1].get_snapshot(session_id).messages[0].content == "B original"

    stores[0].append_turn(
        session_id=session_id, memory_key=session_id,
        context=AgentContext(session_id=session_id),
        messages=[ChatMessage(role="user", content="A updated")],
    )
    assert stores[0].get_snapshot(session_id).messages[0].content == "A updated"
    assert stores[1].get_snapshot(session_id).messages[0].content == "B original"

    stores[0].clear_snapshot(session_id)
    assert stores[0].get_snapshot(session_id) is None
    assert stores[1].get_snapshot(session_id).messages[0].content == "B original"


def test_rejects_missing_workspace_id(mysql_sessions) -> None:
    with pytest.raises(ValueError):
        SqlAgentSessionStore(mysql_sessions, workspace_id="")
