"""Durable Job waiting primitives shared by E2E scenarios."""

from __future__ import annotations

import time
from typing import Any

from tools.e2e_support.api_client import CoreApiClient


TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


def wait_for_job(
    client: CoreApiClient,
    job_id: str,
    *,
    action: str,
    timeout_seconds: float = 300.0,
    require_success: bool = True,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        latest = client.get_job(job_id)
        if latest["status"] in TERMINAL_JOB_STATUSES:
            if require_success and latest["status"] != "succeeded":
                raise RuntimeError(f"{action} job did not succeed: {latest}")
            return latest
        time.sleep(0.5)
    raise RuntimeError(f"{action} job timed out after {timeout_seconds:.0f}s: {latest}")


def wait_for_video_processed(
    client: CoreApiClient,
    series_id: str,
    video_id: str,
    *,
    timeout_seconds: float = 300.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        for series in client.library().get("series", []):
            if series.get("id") != series_id:
                continue
            for video in series.get("videos", []):
                if video.get("id") == video_id:
                    latest = video
                    if video.get("processed") is True:
                        return
        time.sleep(0.5)
    raise RuntimeError(f"Series generation did not process video '{video_id}' within {timeout_seconds:.0f}s: {latest}")


def wait_for_video_source(
    client: CoreApiClient,
    series_id: str,
    video_id: str,
    *,
    timeout_seconds: float = 300.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        for series in client.library().get("series", []):
            if series.get("id") != series_id:
                continue
            for video in series.get("videos", []):
                if video.get("id") == video_id:
                    latest = video
                    if video.get("is_linked") is not True and video.get("status") != "source_missing":
                        return
        time.sleep(0.5)
    raise RuntimeError(f"Linked download did not make video source available within {timeout_seconds:.0f}s: {latest}")


def wait_for_generation_to_settle(
    client: CoreApiClient,
    series_id: str,
    video_id: str,
    *,
    timeout_seconds: float = 60.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = client.get_generation_status(series_id, video_id)
        job_id = status.get("job_id")
        if not isinstance(job_id, str):
            return
        job = wait_for_job(client, job_id, action="generation cleanup", timeout_seconds=max(1.0, deadline - time.monotonic()), require_success=False)
        if job["status"] in TERMINAL_JOB_STATUSES:
            return
    raise RuntimeError(f"Generation job did not settle before cleanup: {series_id}/{video_id}")
