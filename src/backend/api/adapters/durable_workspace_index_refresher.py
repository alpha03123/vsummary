"""Schedules workspace RAG refreshes through the durable Job queue."""

from __future__ import annotations

from collections.abc import Callable

from backend.video_summary.infrastructure.persistence.control_plane_repository import ControlPlaneConflictError


class DurableWorkspaceIndexRefresher:
    """Coalesces all local index mutations into one workspace-scoped Job."""

    def __init__(self, submit: Callable[[], None]) -> None:
        self._submit = submit

    def refresh(self) -> None:
        self._submit()

    def refresh_all(self) -> None:
        self._submit()

    def upsert_video(self, _series_id: str, _video_id: str) -> None:
        self._submit()

    def delete_video(self, _series_id: str, _video_id: str) -> None:
        self._submit()

    def delete_series(self, _series_id: str) -> None:
        self._submit()


def submit_workspace_index_refresh(*, repository, workspace_id: str) -> None:
    try:
        repository.submit(
            workspace_id=workspace_id,
            resource_type="workspace",
            resource_id=workspace_id,
            operation="refresh_rag_index",
            request_payload={"workspace_id": workspace_id},
            active_key=f"workspace:{workspace_id}:refresh_rag_index",
            idempotency_scope_id=None,
            idempotency_key=None,
        )
    except ControlPlaneConflictError:
        # A running refresh reads the current SQL source of truth, so one active
        # workspace refresh coalesces subsequent content mutations safely.
        return
