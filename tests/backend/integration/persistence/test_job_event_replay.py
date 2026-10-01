from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository


def test_completed_job_replays_running_steps_before_its_terminal_event(stored_video, mysql_sessions):
    workspace, series_id, video_id = stored_video
    repository = SqlJobRepository(mysql_sessions)
    operation = "test_progress_replay"
    submitted = repository.submit(
        workspace_id=workspace.workspace_id, resource_type="video", resource_id=video_id,
        operation=operation, request_payload={"series_id": series_id}, active_key=f"replay:{video_id}",
        idempotency_scope_id=None, idempotency_key=None,
    )
    claim = repository.claim(worker_id="replay-test", lease_seconds=60, operations=frozenset({operation}))
    assert claim.id == submitted.id
    repository.append_progress(claim, stage="sample_frames", progress=None, detail="Selecting pictures")
    repository.append_progress(claim, stage="understand_frames", progress=None, detail="Reading pictures")
    repository.succeed(claim, detail="Done")
    events = repository.events(claim.id, after_sequence=0, workspace_id=workspace.workspace_id)
    assert [event.stage for event in events] == ["queued", "claimed", "sample_frames", "understand_frames", "succeeded"]
    assert [event.status for event in events] == ["queued", "running", "running", "running", "succeeded"]
