from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock

from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace


def test_updating_a_note_preserves_its_creation_timestamp() -> None:
    sessions = MagicMock()
    workspace = SqlVideoWorkspace(
        session_factory=sessions,
        blob_store=Mock(),
        cache_root=Path("cache"),
        workspace_id="workspace-1",
    )
    workspace.get_video_source = Mock(return_value=object())
    workspace._refresh_rag = Mock()

    created_at = datetime(2026, 9, 1, 8, 30, tzinfo=timezone.utc)
    session = sessions.begin.return_value.__enter__.return_value
    session.execute.side_effect = [Mock(rowcount=1), Mock(scalar_one=Mock(return_value=created_at)), Mock()]

    note = workspace.update_video_note(
        "series-1",
        "video-1",
        "note-1",
        title="更新后的标题",
        content="更新后的内容",
    )

    assert note is not None
    assert note.created_at == "2026-09-01T08:30:00+00:00"
    assert note.updated_at
