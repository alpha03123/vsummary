"""Lifecycle management for temporary E2E series and their durable Jobs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from tools.e2e_support.api_client import CoreApiClient
from tools.e2e_support.jobs import wait_for_generation_to_settle, wait_for_job


@dataclass
class E2EResourceScope:
    client: CoreApiClient
    cleanup_timeout_seconds: float = 60.0
    _series: list[tuple[str, str | None]] = field(default_factory=list)
    _job_ids: list[str] = field(default_factory=list)

    def track_series(self, series_id: str, video_id: str | None = None) -> None:
        self._series.append((series_id, video_id))

    def track_job(self, submission: dict[str, object]) -> str:
        job_id = submission.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeError(f"Job submission did not return job_id: {submission}")
        self._job_ids.append(job_id)
        return job_id

    def cleanup(self) -> None:
        for series_id, video_id in self._series:
            status_code = self.client.cancel_series_generation(series_id)
            if status_code == 404 and video_id is not None:
                status_code = self.client.cancel_video_generation(series_id, video_id)
            if status_code not in {200, 404}:
                raise RuntimeError(f"cancel E2E series generation failed with HTTP {status_code}: {series_id}")
        for job_id in self._job_ids:
            wait_for_job(self.client, job_id, action="E2E cleanup", timeout_seconds=self.cleanup_timeout_seconds, require_success=False)
        for series_id, video_id in self._series:
            if video_id is not None:
                wait_for_generation_to_settle(self.client, series_id, video_id, timeout_seconds=self.cleanup_timeout_seconds)
            self._delete_series_when_quiescent(series_id)

    def _delete_series_when_quiescent(self, series_id: str) -> None:
        deadline = time.monotonic() + self.cleanup_timeout_seconds
        while True:
            response = self.client.delete_series(series_id)
            if response.is_success:
                if not any(item.get("id") == series_id for item in self.client.library().get("series", [])):
                    return
                raise RuntimeError(f"E2E series still exists after deletion: {series_id}")
            if response.status_code != 409 or time.monotonic() >= deadline:
                raise RuntimeError(f"delete E2E series failed with HTTP {response.status_code}: {response.text}")
            time.sleep(0.5)

    def __enter__(self) -> "E2EResourceScope":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.cleanup()
        return False
