from __future__ import annotations

import unittest

from backend.core.errors import ActiveJobConflictError
from backend.video_summary.library.usecases.mutations import (
    DeleteSeries,
    DeleteVideoSource,
    GenerationInProgressError,
)


class _IndexRefresher:
    def delete_series(self, _series_id: str) -> None:
        raise AssertionError("Index must not mutate after a Job conflict.")

    def delete_video(self, _series_id: str, _video_id: str) -> None:
        raise AssertionError("Index must not mutate after a Job conflict.")


class _ConflictWorkspace:
    def list_series(self):
        return []

    def get_video_source(self, _series_id: str, _video_id: str):
        return None

    def delete_series(self, _series_id: str) -> bool:
        raise ActiveJobConflictError("active job")

    def delete_video(self, _series_id: str, _video_id: str) -> bool:
        raise ActiveJobConflictError("active job")


class DurableJobDeletionConflictTests(unittest.TestCase):
    def test_series_delete_maps_durable_job_conflict(self) -> None:
        with self.assertRaisesRegex(GenerationInProgressError, "active job"):
            DeleteSeries(_ConflictWorkspace(), _IndexRefresher()).run("series-1")

    def test_video_delete_maps_durable_job_conflict(self) -> None:
        with self.assertRaisesRegex(GenerationInProgressError, "active job"):
            DeleteVideoSource(_ConflictWorkspace(), _IndexRefresher()).run("series-1", "video-1")
