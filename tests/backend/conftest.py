"""Database fixtures shared by backend integration tests."""

from __future__ import annotations

import os

import pytest

from backend.core.ids import new_ulid
from backend.local.persistence.file_blob_store import FileBlobStore
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.database import DatabaseOptions, create_session_factory
from backend.video_summary.infrastructure.persistence.models import ExternalMediaReference
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace


@pytest.fixture(scope="session")
def mysql_sessions():
    url = os.environ.get("VSUMMARY_TEST_MYSQL_URL")
    if not url:
        pytest.skip("Run tools/run_backend_tests.py --mysql-home <runtime> for MySQL integration tests.")
    sessions = create_session_factory(DatabaseOptions(url=url))
    try:
        yield sessions
    finally:
        sessions.kw["bind"].dispose()


@pytest.fixture
def stored_video(mysql_sessions, tmp_path):
    control = SqlControlPlaneRepository(mysql_sessions)
    workspace_id = control.create_workspace(owner_scope_id=f"test-{new_ulid()}", title="Test workspace")
    series_id = control.create_series(workspace_id=workspace_id, title="Series", position=0)
    video_id = control.create_video(series_id=series_id, title="Video", source_kind="local")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"test video")
    with mysql_sessions.begin() as session:
        session.add(ExternalMediaReference(video_id=video_id, source_path=str(source)))
    workspace = SqlVideoWorkspace(
        session_factory=mysql_sessions,
        blob_store=FileBlobStore(tmp_path / "blobs"),
        cache_root=tmp_path / "cache",
        workspace_id=workspace_id,
    )
    return workspace, series_id, video_id
