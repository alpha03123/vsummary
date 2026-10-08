"""Schedules workspace RAG refreshes through the durable Job queue."""

from __future__ import annotations

from collections.abc import Callable


INDEX_CHANGE_EVENTS = {
    "content_published": "upsert_video",
    "note_published": "upsert_video",
    "knowledge_cards_published": "upsert_video",
    "video_changed": "upsert_video",
    "video_deleted": "delete_video",
    "series_changed": "refresh_series",
    "series_deleted": "delete_series",
}

class DurableWorkspaceIndexRefresher:
    """Coalesces all local index mutations into one workspace-scoped Job."""

    def __init__(self, submit: Callable[..., None]) -> None:
        self._submit = submit

    def refresh(self) -> None:
        self._submit()

    def refresh_all(self) -> None:
        self._submit()

    def upsert_video(self, series_id: str, video_id: str) -> None:
        self._submit(action="upsert_video", series_id=series_id, video_id=video_id)

    def delete_video(self, series_id: str, video_id: str) -> None:
        self._submit(action="delete_video", series_id=series_id, video_id=video_id)

    def delete_series(self, series_id: str) -> None:
        self._submit(action="delete_series", series_id=series_id)


def submit_workspace_index_refresh(*, repository, workspace_id: str, **change) -> None:
    repository.request_index_refresh(workspace_id, **change)


def submit_workspace_index_event(*, repository, event) -> None:
    action = INDEX_CHANGE_EVENTS[event.event_type]
    resource = {"video_id": event.payload["video_id"], "series_id": event.payload.get("series_id")} if action in {"upsert_video", "delete_video"} else {
        "series_id": event.payload["series_id"]
    }
    submit_workspace_index_refresh(repository=repository, workspace_id=event.workspace_id, action=action, **resource)
