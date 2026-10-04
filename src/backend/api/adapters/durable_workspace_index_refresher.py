"""Schedules workspace RAG refreshes through the durable Job queue."""

from __future__ import annotations

from collections.abc import Callable



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
    repository.request_index_refresh(workspace_id)
