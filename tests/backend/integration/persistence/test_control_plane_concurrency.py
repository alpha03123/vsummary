from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError, SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.models import Job, JobEvent, Series


def test_concurrent_playground_creation_reuses_one_series(stored_video, mysql_sessions) -> None:
    workspace, _, _ = stored_video
    control = SqlControlPlaneRepository(mysql_sessions)
    ready = Barrier(2)

    def create():
        ready.wait(timeout=10)
        return control.ensure_playground_series(workspace_id=workspace.workspace_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: create(), range(2)))
    assert ids[0] == ids[1]
    with mysql_sessions() as session:
        rows = session.scalars(select(Series).where(Series.workspace_id == workspace.workspace_id, Series.source_kind == "playground")).all()
    assert len(rows) == 1


def test_concurrent_active_job_submission_commits_one_job_and_event(stored_video, mysql_sessions) -> None:
    workspace, series_id, video_id = stored_video
    control = SqlControlPlaneRepository(mysql_sessions)
    ready = Barrier(2)

    def submit():
        ready.wait(timeout=10)
        try:
            return control.submit_job(
                workspace_id=workspace.workspace_id, resource_type="video", resource_id=video_id,
                operation="generate_summary", request_payload={"series_id": series_id, "video_id": video_id},
                active_key=f"video:{video_id}:generate_summary",
            )
        except ControlPlaneConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted = list(pool.map(lambda _: submit(), range(2)))
    assert sum(item is not None for item in submitted) == 1
    with mysql_sessions() as session:
        jobs = session.scalars(select(Job).where(Job.workspace_id == workspace.workspace_id)).all()
        events = session.scalars(select(JobEvent).join(Job).where(Job.workspace_id == workspace.workspace_id)).all()
    assert len(jobs) == len(events) == 1
    assert events[0].job_id == jobs[0].id


def test_external_video_identity_is_unique_within_its_series(stored_video, mysql_sessions) -> None:
    workspace, series_id, _ = stored_video
    control = SqlControlPlaneRepository(mysql_sessions)
    first = control.create_video(series_id=series_id, title="First", source_kind="youtube", external_source_id="same-source")
    with pytest.raises(IntegrityError):
        control.create_video(series_id=series_id, title="Duplicate", source_kind="youtube", external_source_id="same-source")
    other_series = control.create_series(workspace_id=workspace.workspace_id, title="Other", position=1)
    second = control.create_video(series_id=other_series, title="Allowed", source_kind="youtube", external_source_id="same-source")
    assert first != second


def test_series_position_is_unique_within_its_workspace(stored_video, mysql_sessions) -> None:
    workspace, _, _ = stored_video
    control = SqlControlPlaneRepository(mysql_sessions)
    with pytest.raises(IntegrityError):
        control.create_series(workspace_id=workspace.workspace_id, title="Duplicate position", position=0)
    other_workspace = control.create_workspace(owner_scope_id="test-position", title="Other workspace")
    assert control.create_series(workspace_id=other_workspace, title="Allowed", position=0)
