"""Durable Job query, cancellation and SSE endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.dependencies import JobRepositoryDep, WorkspaceServicesDep, get_workspace_context
from backend.video_summary.infrastructure.rag.rag_models import rag_index_embedding_required_message
from backend.core.context import WorkspaceContext
from backend.core.jobs import job_snapshot_payload


router = APIRouter()


@router.get("/api/workspace/index/status")
def workspace_index_status(job_repository: JobRepositoryDep, services: WorkspaceServicesDep,
    context: WorkspaceContext = Depends(get_workspace_context), series_id: str | None = None):
    from backend.api.adapters.job_status import durable_status
    status = durable_status(job_repository, workspace_id=context.workspace_id,
        resource_id=context.workspace_id, operations=("refresh_rag_index",))
    try:
        health = services.inspect_agent_workspace_indexes(
            job_repository.index_refresh_plan(context.workspace_id), series_id=series_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {**status, **health}


@router.post("/api/workspace/index/refresh", status_code=202)
def refresh_workspace_index(job_repository: JobRepositoryDep, services: WorkspaceServicesDep,
    context: WorkspaceContext = Depends(get_workspace_context)):
    # A rebuild without the local embedding model can only fail; point the user at the download instead.
    if services.embedding_provider == "fastembed" and not services.rag_model_manager.is_downloaded("embedding"):
        raise HTTPException(status_code=409, detail=rag_index_embedding_required_message())
    job_repository.request_index_refresh(context.workspace_id)
    return {"status": "queued"}

_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


@router.get("/api/jobs")
def list_jobs(job_repository: JobRepositoryDep, context: WorkspaceContext = Depends(get_workspace_context),
              status: str | None = None, operation: str | None = None, offset: int = 0, limit: int = 50):
    try:
        result = job_repository.list_jobs(workspace_id=context.workspace_id, actor_id=context.actor_id,
                                          status=status, operation=operation, offset=offset, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"total": result["total"], "items": [job_snapshot_payload(item) for item in result["items"]]}


@router.get("/api/jobs/stats")
def job_statistics(job_repository: JobRepositoryDep, context: WorkspaceContext = Depends(get_workspace_context)):
    return {"by_status": job_repository.job_statistics(workspace_id=context.workspace_id, actor_id=context.actor_id)}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, job_repository: JobRepositoryDep, context: WorkspaceContext = Depends(get_workspace_context)) -> dict[str, object]:
    snapshot = job_repository.get(job_id, workspace_id=context.workspace_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = job_snapshot_payload(snapshot)
    if snapshot.operation == "generate_series_batch":
        children = job_repository.children(job_id, workspace_id=context.workspace_id)
        payload["children"] = [job_snapshot_payload(child) for child in children]
        payload["dispatch_complete"] = snapshot.status == "succeeded"
        payload["batch_complete"] = snapshot.status in _TERMINAL_STATUSES and all(child.status in _TERMINAL_STATUSES for child in children)
    return payload


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, job_repository: JobRepositoryDep, context: WorkspaceContext = Depends(get_workspace_context)) -> dict[str, object]:
    snapshot = job_repository.request_cancel(job_id, workspace_id=context.workspace_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job_snapshot_payload(snapshot)


@router.get("/api/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    job_repository: JobRepositoryDep,
    context: WorkspaceContext = Depends(get_workspace_context),
    after_sequence: int = 0,
) -> StreamingResponse:
    if after_sequence < 0:
        raise HTTPException(status_code=400, detail="after_sequence cannot be negative")
    if job_repository.get(job_id, workspace_id=context.workspace_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        sequence = after_sequence
        while True:
            snapshot = job_repository.get(job_id, workspace_id=context.workspace_id)
            if snapshot is None:
                break
            events = job_repository.events(job_id, after_sequence=sequence, workspace_id=context.workspace_id)
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
                    "started_at": event.started_at.timestamp() if event.started_at is not None else None,
                }
                yield f"id: {event.sequence}\nevent: progress\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            # 先读任务状态再取事件，保证看到终态时也已读到同一事务里的完成事件。
            if snapshot.status in _TERMINAL_STATUSES:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

