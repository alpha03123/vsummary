"""Workspace-scoped durable progress used by browser clients."""


def durable_status(repository, *, workspace_id: str, resource_id: str, operations: tuple[str, ...], batch: bool = False):
    job = repository.latest_for_resource(workspace_id=workspace_id, resource_id=resource_id, operations=operations)
    if job is None:
        return {"status": "idle", "progress": None, "detail": None, "job_id": None}
    children = repository.children(job.id, workspace_id=workspace_id) if batch else []
    terminal = {"succeeded", "failed", "cancelled"}
    status = job.status
    finished = sum(child.status in terminal for child in children)
    if batch and children and job.status in terminal:
        if finished < len(children):
            status = "cancelling" if job.cancel_requested else "running"
        elif any(child.status == "failed" for child in children):
            status = "failed"
        elif any(child.status == "cancelled" for child in children):
            status = "cancelled"
        else:
            status = "succeeded"
    event = repository.latest_event(job.id, workspace_id=workspace_id)
    progress = finished / len(children) * 100 if children else event.progress if event else 0
    detail = f"已结束 {finished}/{len(children)} 个视频任务" if children else job.failure_detail or (event.detail if event else None)
    return {"job_id": job.id, "status": status, "stage": event.stage if event else status,
        "progress": progress, "detail": detail, "error": job.failure_detail if status == "failed" else None,
        "started_at": job.started_at.timestamp() if job.started_at else None,
        "elapsed_seconds": max(0, (event.occurred_at - job.started_at).total_seconds()) if event and job.started_at else None,
        "total": len(children), "finished": finished}
