"""Workspace-scoped durable progress used by browser clients."""


def durable_status(repository, *, workspace_id: str, resource_id: str, operations: tuple[str, ...], batch: bool = False, job_id: str | None = None):
    job = repository.get(job_id, workspace_id=workspace_id) if job_id is not None else repository.latest_for_resource(workspace_id=workspace_id, resource_id=resource_id, operations=operations)
    if job_id is not None and (job is None or job.resource_id != resource_id or job.operation not in operations):
        raise LookupError("generation job not found")
    if job is None:
        return {"status": "idle", "progress": None, "detail": None, "job_id": None}
    children = repository.children(job.id, workspace_id=workspace_id) if batch else []
    terminal = {"succeeded", "failed", "cancelled"}
    status = "running" if batch and job.status == "waiting_children" else job.status
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
    history = repository.events(job.id, after_sequence=0, workspace_id=workspace_id)
    event = history[-1] if history else None
    progress = max((item.progress for item in history if item.progress is not None), default=0)
    detail = f"已结束 {finished}/{len(children)} 个视频任务" if children else job.failure_detail or (event.detail if event else None)
    if children:
        child_histories = [(child, repository.events(child.id, after_sequence=0, workspace_id=workspace_id)) for child in children]
        progress = sum(100 if child.status in terminal else
            max((item.progress for item in events if item.progress is not None), default=0)
            for child, events in child_histories) / len(children)
        active = [(child, events) for child, events in child_histories if child.status in {'running', 'cancelling'} and events]
        if active:
            _, history = max(active, key=lambda pair: pair[1][-1].occurred_at)
            event = history[-1]
            if event.detail:detail += f"；{event.detail}"
    return {"job_id": job.id, "status": status, "stage": event.stage if event else status,
        "sequence": event.sequence if event and not batch else None,
        "progress": progress, "detail": detail, "error": job.failure_detail if status == "failed" else None,
        "started_at": job.started_at.timestamp() if job.started_at else None,
        "elapsed_seconds": max(0, (event.occurred_at - job.started_at).total_seconds()) if event and job.started_at else None,
        "total": len(children), "finished": finished,
        "events": [{"status": item.status, "stage": item.stage, "detail": item.detail, "progress": item.progress} for item in history]}
