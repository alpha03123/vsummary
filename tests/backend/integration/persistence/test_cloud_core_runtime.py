from datetime import timedelta
from pathlib import Path
from shutil import copyfile

import pytest
from sqlalchemy import select, func

from backend.api.di.bootstrap import build_host_container
from backend.api.di.sql_workspace_services import SqlWorkspaceServicesProvider
from backend.core.capabilities import CapabilitySet
from backend.core.context import WorkspaceContext
from backend.core.quota import UnlimitedQuotaGuard, NoopUsageMeter
from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.execution_context import bind_execution_claim, JobLeaseLostError
from backend.video_summary.infrastructure.persistence.file_blob_store import FileBlobStore
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from backend.video_summary.infrastructure.persistence.models import Job


def test_same_host_resolves_multiple_workspace_service_graphs(mysql_sessions, tmp_path):
    (tmp_path / "config").mkdir()
    copyfile(Path(__file__).resolve().parents[4] / "config/settings.toml.example", tmp_path / "config/settings.toml")
    control = SqlControlPlaneRepository(mysql_sessions)
    a = control.create_workspace(owner_scope_id="a", title="A")
    b = control.create_workspace(owner_scope_id="b", title="B")
    provider = SqlWorkspaceServicesProvider(session_factory=mysql_sessions, blob_store=FileBlobStore(tmp_path / "blobs"), data_root=tmp_path)
    container = build_host_container(tmp_path, session_factory=mysql_sessions, workspace_services_provider=provider,
        quota_guard=UnlimitedQuotaGuard(), usage_meter=NoopUsageMeter(), capabilities=CapabilitySet())
    provider.install_host(container)
    try:
        sa = provider.get_services(WorkspaceContext(a, "user-a", "request-a"))
        sb = provider.get_services(WorkspaceContext(b, "user-b", "request-b"))
        assert sa.check_health().id == a and sa.check_health().title == "A"
        assert sb.check_health().id == b and sb.check_health().title == "B"
        assert provider.get_services(WorkspaceContext(a, "user-a", "again")).check_health().id == a
    finally:
        container.model_http_client.close()


def test_content_mutation_during_refresh_queues_a_followup(mysql_sessions):
    workspace_id = SqlControlPlaneRepository(mysql_sessions).create_workspace(owner_scope_id="index-test", title="Index")
    repository = SqlJobRepository(mysql_sessions)
    repository.request_index_refresh(workspace_id)
    claim = repository.claim(worker_id="index-worker", lease_seconds=120, operations=frozenset({"refresh_rag_index"}))
    assert claim.workspace_id == workspace_id
    target = repository.index_refresh_revision(workspace_id)
    repository.request_index_refresh(workspace_id)
    repository.complete_index_refresh(claim, target, "generation-one")
    repository.succeed(claim, detail="indexed")
    next_claim = repository.claim(worker_id="index-worker", lease_seconds=120, operations=frozenset({"refresh_rag_index"}))
    assert next_claim is not None and next_claim.id != claim.id
    assert repository.index_refresh_revision(workspace_id) > target
    repository.complete_index_refresh(next_claim, repository.index_refresh_revision(workspace_id), "generation-two")
    repository.succeed(next_claim, detail="indexed")


def test_expired_attempt_cannot_save_knowledge_cards(stored_video, mysql_sessions):
    workspace, series_id, video_id = stored_video
    repository = SqlJobRepository(mysql_sessions)
    submitted = repository.submit(workspace_id=workspace.workspace_id, resource_type="video", resource_id=video_id,
        operation="generate_video_knowledge_cards", request_payload={"series_id": series_id},
        active_key=f"cards:{video_id}", idempotency_scope_id=None, idempotency_key=None)
    claim = repository.claim(worker_id="stale", lease_seconds=120, operations=frozenset({"generate_video_knowledge_cards"}))
    with mysql_sessions.begin() as session:
        job = session.get(Job, submitted.id)
        job.lease_expires_at = session.scalar(select(func.now())) - timedelta(seconds=1)
    with bind_execution_claim(claim), pytest.raises(JobLeaseLostError):
        workspace.save_video_knowledge_cards(series_id, video_id, title="stale", cards=[])
