from io import BytesIO

import pytest
from sqlalchemy import select, text

from backend.api.adapters.durable_workspace_index_refresher import submit_workspace_index_event
from backend.core.ids import new_ulid
from backend.core.errors import ActiveJobConflictError
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from backend.video_summary.infrastructure.persistence.models import (
    Artifact, OutboxEvent, Video, Series, Job, Summary, SummaryChapter, VideoContentState,
)
from backend.video_summary.library.models import KnowledgeCardDTO, AiSummaryVisualEvidenceDTO
from backend.video_summary.infrastructure.persistence.outbox_repository import SqlOutboxRepository
from backend.video_summary.infrastructure.persistence.outbox_worker import SqlOutboxWorker
from backend.video_summary.infrastructure.persistence.sql_rag_source import SqlRagSourceRepository


@pytest.fixture(autouse=True)
def cancel_background_jobs(stored_video, mysql_sessions):
    yield
    workspace = stored_video[0]
    repository = SqlJobRepository(mysql_sessions)
    with mysql_sessions() as session:
        ids = session.scalars(select(Job.id).where(Job.workspace_id == workspace.workspace_id,
            Job.status.in_(("queued", "retrying", "running", "cancelling")))).all()
    for job_id in ids:
        repository.request_cancel(job_id, workspace_id=workspace.workspace_id)


@pytest.mark.parametrize("storage_mode", ["copy", "hardlink", "external_reference"])
@pytest.mark.parametrize("delete_series", [False, True])
def test_hard_delete_cleans_owned_content_and_preserves_original(
    stored_video, mysql_sessions, tmp_path, storage_mode, delete_series,
):
    workspace, original_series, original_video = stored_video
    source = tmp_path / "original.mp4"
    source.write_bytes(b"original media")
    imported = workspace.import_local_series_from_paths(title="Imported", source_paths=[source], storage_mode=storage_mode)
    series_id = imported.id
    video_id = imported.videos[0].id
    workspace.create_video_note(series_id, video_id, title="Note", content="Owned content", source="manual")
    workspace.save_video_ai_summary(series_id, video_id, title="AI", content="AI content")
    workspace.save_video_ai_summary_visual_evidence(series_id, video_id,
        frames=[AiSummaryVisualEvidenceDTO(timestamp_seconds=1, text="Image evidence")])
    workspace.save_video_knowledge_cards(series_id, video_id, title="Cards",
        cards=[KnowledgeCardDTO("card", "Card", "concept", "Summary", "Details", [], [], [])])
    workspace.save_video_mindmap(series_id, video_id, mindmap={"id": "root", "title": "Map", "children": []})
    workspace.save_series_mindmap(series_id, mindmap={"id": "root", "title": "Series", "children": []})
    workspace.save_series_catalog(series_id, {"title": "Catalog"})
    SqlRagSourceRepository(mysql_sessions).refresh_video(workspace_id=workspace.workspace_id, series_id=series_id, video_id=video_id)
    artifact = tmp_path / "raw.srt"
    artifact.write_text("transcript", encoding="utf-8")
    workspace.save_generated_artifact(video_id=video_id, kind="transcript", source_path=artifact, media_type="text/plain")
    with mysql_sessions.begin() as session:
        artifact_id = session.scalar(select(Artifact.id).where(Artifact.video_id == video_id))
        session.execute(text("INSERT INTO transcripts (video_id,content_version,language,source_type,raw_srt_artifact_id) VALUES (:video,1,'zh','asr',:artifact)"), {"video": video_id, "artifact": artifact_id})
        session.execute(text("INSERT INTO transcript_segments (id,video_id,content_version,ordinal,start_ms,end_ms,text) VALUES (:id,:video,1,0,0,1000,'text')"), {"id": new_ulid(), "video": video_id})
        session.add(Summary(video_id=video_id, content_version=1, title="Summary", markdown="Content", payload={}, content_format_version=1))
        session.add(SummaryChapter(id=new_ulid(), video_id=video_id, content_version=1, ordinal=0, title="Chapter", body="Text", payload={}))
        session.add(VideoContentState(video_id=video_id, content_version=1, transcript_version=1, summary_version=1, cards_version=1, mindmap_version=1))
    source_view = workspace.get_video_source(series_id, video_id)
    source_view.output_dir.mkdir(parents=True, exist_ok=True)
    (source_view.output_dir / "output.txt").write_text("derived", encoding="utf-8")
    workspace.materialize_artifact(video_id=video_id, kind="transcript", filename="raw.srt")
    cached_asr = workspace.cache_root / "generation-stages" / video_id
    cached_asr.mkdir(parents=True)
    (cached_asr / "audio.wav").write_bytes(b"derived audio")
    with mysql_sessions() as session:
        keys = list(session.execute(text("SELECT blob_key FROM media_objects WHERE video_id=:video UNION ALL SELECT blob_key FROM artifacts WHERE video_id=:video"), {"video": video_id}).scalars())
        chunks = list(session.execute(text("SELECT c.id FROM rag_chunks c JOIN rag_documents d ON d.id=c.document_id WHERE d.video_id=:video"), {"video": video_id}).scalars())
    assert chunks
    assert workspace.delete_series(series_id) if delete_series else workspace.delete_video(series_id, video_id)
    assert source.read_bytes() == b"original media"
    assert not cached_asr.exists()
    assert not source_view.output_dir.exists()
    assert all(not (tmp_path / "blobs" / "objects" / key).exists() for key in keys)
    with mysql_sessions() as session:
        assert session.get(Video, video_id) is None
        assert session.get(Video, original_video) is not None
        assert session.get(Series, original_series) is not None
        for table in ("media_objects", "external_media_references", "artifacts", "transcripts", "transcript_segments",
                "notes", "ai_summaries", "ai_summary_visual_evidence", "mindmaps", "rag_documents",
                "summaries", "summary_chapters", "video_content_state", "knowledge_cards", "knowledge_card_sets"):
            assert session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE video_id=:video"), {"video": video_id}).scalar_one() == 0
        assert (session.get(Series, series_id) is None) == delete_series
    assert not (workspace.delete_series(series_id) if delete_series else workspace.delete_video(series_id, video_id))
    # Older content notifications must still resolve to deletion after SQL rows disappear.
    repository = SqlJobRepository(mysql_sessions)
    with pytest.raises(LookupError):
        repository.submit(workspace_id=workspace.workspace_id,
            resource_type="series" if delete_series else "video", resource_id=series_id if delete_series else video_id,
            operation="generate_series_batch" if delete_series else "generate_summary", request_payload={},
            active_key=f"deleted:{video_id}", idempotency_scope_id=None, idempotency_key=None)
    outbox = SqlOutboxRepository(mysql_sessions)
    for event in outbox.claim_batch(workspace_id=workspace.workspace_id, worker_id="delete-test", lease_seconds=60, max_attempts=5):
        if event.event_type == "resource_cleanup_requested":
            workspace.delete_resource_files(event.payload)
        else:
            submit_workspace_index_event(repository=repository, event=event)
        outbox.confirm_delivered(event)
    changes = repository.index_refresh_plan(workspace.workspace_id).changes
    assert changes and all(change["action"].startswith("delete_") for change in changes)
    other_workspace = SqlControlPlaneRepository(mysql_sessions).create_workspace(owner_scope_id=new_ulid(), title="Other")
    with pytest.raises(LookupError):
        repository.request_index_refresh(other_workspace, action="delete_video", series_id=series_id, video_id=video_id)


def test_series_delete_includes_series_artifacts_and_rolls_back_on_sql_failure(stored_video, mysql_sessions, tmp_path, monkeypatch):
    workspace, series_id, video_id = stored_video
    staged = workspace.blob_store.put_staging(job_id="series-artifact", source=BytesIO(b"series data"), content_type="application/json")
    reference = workspace.blob_store.commit(staged, object_key=f"series/{series_id}/catalog.json")
    with mysql_sessions.begin() as session:
        session.add(Artifact(id=new_ulid(), workspace_id=workspace.workspace_id, series_id=series_id,
            kind="catalog", blob_key=reference.key, sha256=reference.sha256, byte_size=reference.byte_size, media_type=reference.content_type))
    original = workspace._enqueue_index_change
    def fail(*args, **kwargs):
        raise RuntimeError("injected transaction failure")
    monkeypatch.setattr(workspace, "_enqueue_index_change", fail)
    with pytest.raises(RuntimeError):
        workspace.delete_series(series_id)
    with mysql_sessions() as session:
        assert session.get(Series, series_id) is not None
        assert session.get(Video, video_id) is not None
    assert workspace.blob_store.stat(reference).byte_size == len(b"series data")
    monkeypatch.setattr(workspace, "_enqueue_index_change", original)
    assert workspace.delete_series(series_id)
    assert not (tmp_path / "blobs" / "objects" / reference.key).exists()


def test_file_cleanup_failure_is_durable_and_retryable(stored_video, mysql_sessions, monkeypatch):
    workspace, series_id, video_id = stored_video
    note = workspace.cache_root / "jobs" / video_id / "note.txt"
    note.parent.mkdir(parents=True)
    note.write_text("derived content", encoding="utf-8")
    cleanup = workspace.delete_resource_files
    def fail(_payload):
        raise PermissionError("injected file lock")
    monkeypatch.setattr(workspace, "delete_resource_files", fail)
    with pytest.raises(PermissionError):
        workspace.delete_video(series_id, video_id)
    with mysql_sessions() as session:
        assert session.get(Video, video_id) is None
    repository = SqlOutboxRepository(mysql_sessions)
    worker = SqlOutboxWorker(repository=repository, workspace_id=workspace.workspace_id,
        handlers={"resource_cleanup_requested": lambda event: cleanup(event.payload)})
    events = repository.claim_batch(workspace_id=workspace.workspace_id, worker_id="retry-test", lease_seconds=60, max_attempts=5)
    event = next(event for event in events if event.event_type == "resource_cleanup_requested")
    worker._dispatch(event)
    assert not note.exists()
    with mysql_sessions() as session:
        assert session.get(OutboxEvent, event.id).delivered_at is not None


@pytest.mark.parametrize("delete_series", [False, True])
def test_active_jobs_block_hard_deletion(stored_video, mysql_sessions, delete_series):
    workspace, series_id, video_id = stored_video
    SqlJobRepository(mysql_sessions).submit(workspace_id=workspace.workspace_id, resource_type="video", resource_id=video_id,
        operation="generate_summary", request_payload={"series_id": series_id}, active_key=f"active:{video_id}",
        idempotency_scope_id=None, idempotency_key=None)
    with pytest.raises(ActiveJobConflictError):
        workspace.delete_series(series_id) if delete_series else workspace.delete_video(series_id, video_id)
    with mysql_sessions() as session:
        assert session.get(Video, video_id) is not None


def test_deleting_empty_series(stored_video, mysql_sessions):
    workspace = stored_video[0]
    series_id = SqlControlPlaneRepository(mysql_sessions).create_series_at_next_position(
        workspace_id=workspace.workspace_id, title="Empty")
    assert workspace.delete_series(series_id)
    with mysql_sessions() as session:
        assert session.get(Series, series_id) is None
