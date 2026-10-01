from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select, text

from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.models import OutboxEvent


def test_updating_note_preserves_creation_time_and_persists_new_content(stored_video, mysql_sessions) -> None:
    workspace, series_id, video_id = stored_video
    note = workspace.create_video_note(series_id, video_id, title="Original", content="Original content", source="manual")
    original_time = datetime(2020, 1, 1)
    with mysql_sessions.begin() as session:
        session.execute(text("UPDATE notes SET created_at=:created WHERE id=:id"), {"id": note.id, "created": original_time})

    updated = workspace.update_video_note(series_id, video_id, note.id, title=" Updated ", content=" New content ")

    assert updated.created_at == original_time.isoformat()
    reloaded = workspace.get_video_notes(series_id, video_id).notes
    assert len(reloaded) == 1
    assert reloaded[0].title == "Updated"
    assert reloaded[0].content == "New content"
    assert reloaded[0].created_at == original_time.isoformat()
    assert datetime.fromisoformat(reloaded[0].updated_at) > original_time
    with mysql_sessions() as session:
        events = session.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == note.id)).all()
    assert len(events) == 2
    assert all(event.workspace_id == workspace.workspace_id and event.payload["video_id"] == video_id for event in events)


def test_note_and_outbox_roll_back_together(stored_video, mysql_sessions, monkeypatch) -> None:
    workspace, series_id, video_id = stored_video
    note = workspace.create_video_note(series_id, video_id, title="Original", content="Keep this", source="manual")

    def fail_outbox(*_args, **_kwargs):
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr("backend.video_summary.infrastructure.persistence.sql_video_workspace._enqueue_outbox_event", fail_outbox)
    with pytest.raises(RuntimeError):
        workspace.update_video_note(series_id, video_id, note.id, title="Lost", content="Must roll back")
    reloaded = workspace.get_video_notes(series_id, video_id).notes[0]
    assert (reloaded.title, reloaded.content) == ("Original", "Keep this")
    with mysql_sessions() as session:
        events = session.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == note.id)).all()
    assert len(events) == 1


def test_note_from_another_video_cannot_be_updated(stored_video, mysql_sessions) -> None:
    workspace, series_id, video_id = stored_video
    note = workspace.create_video_note(series_id, video_id, title="Original", content="Keep this", source="manual")
    other_video_id = SqlControlPlaneRepository(mysql_sessions).create_video(series_id=series_id, title="Other", source_kind="local")
    with mysql_sessions.begin() as session:
        session.execute(text("INSERT INTO external_media_references (video_id,source_path) SELECT :other,source_path FROM external_media_references WHERE video_id=:video"), {"other": other_video_id, "video": video_id})
    assert workspace.update_video_note(series_id, other_video_id, note.id, title="Wrong video", content="Wrong content") is None
    assert workspace.get_video_notes(series_id, video_id).notes[0].content == "Keep this"
