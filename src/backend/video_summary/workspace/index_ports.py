from __future__ import annotations

from typing import Protocol


class WorkspaceIndexInvalidator(Protocol):
    def invalidate(self) -> None:
        ...


class WorkspaceIndexRefresher(Protocol):
    def refresh_all(self) -> None:
        ...

    def refresh(self) -> None:
        ...

    def upsert_video(self, series_id: str, video_id: str) -> None:
        ...

    def delete_video(self, series_id: str, video_id: str) -> None:
        ...

    def delete_series(self, series_id: str) -> None:
        ...


class SeriesKnowledgeMemoryRefresher(Protocol):
    def refresh(self, series_id: str, video_id: str):
        ...


class GenerationActivityChecker(Protocol):
    def is_video_generation_active(self, series_id: str, video_id: str) -> bool:
        ...

    def is_series_generation_active(self, series_id: str) -> bool:
        ...