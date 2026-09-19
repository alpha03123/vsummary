"""Durable Job query, cancellation and SSE endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.di.container import ApiContainerDep


router = APIRouter()
_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, container: ApiContainerDep) -> dict[str, object]:
    snapshot = container.job_repository.get(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _snapshot_payload(snapshot)


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, container: ApiContainerDep) -> dict[str, object]:
    snapshot = container.job_repository.request_cancel(job_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _snapshot_payload(snapshot)


@router.get("/api/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    container: ApiContainerDep,
    after_sequence: int = 0,
) -> StreamingResponse:
    if after_sequence < 0:
        raise HTTPException(status_code=400, detail="after_sequence cannot be negative")
    if container.job_repository.get(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        sequence = after_sequence
        while True:
            events = container.job_repository.events(job_id, after_sequence=sequence)
            for event in events:
                sequence = event.sequence
                payload = {
                    "job_id": job_id,
                    "sequence": event.sequence,
                    "status": event.status,
                    "stage": event.stage,
                    "progress": event.progress,
                    "detail": event.detail,
                    "occurred_at": event.occurred_at.isoformat(),
                }
                yield f"id: {event.sequence}\nevent: progress\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            snapshot = container.job_repository.get(job_id)
            if snapshot is None or snapshot.status in _TERMINAL_STATUSES:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _snapshot_payload(snapshot) -> dict[str, object]:
    return {
        "job_id": snapshot.id,
        "workspace_id": snapshot.workspace_id,
        "resource": {"type": snapshot.resource_type, "id": snapshot.resource_id},
        "operation": snapshot.operation,
        "status": snapshot.status,
        "attempt_count": snapshot.attempt_count,
        "max_attempts": snapshot.max_attempts,
        "cancel_requested": snapshot.cancel_requested,
        "failure_code": snapshot.failure_code,
        "failure_detail": snapshot.failure_detail,
        "result_content_version": snapshot.result_content_version,
    }
