"""Complete production job snapshots for tests at repository boundaries."""

from datetime import datetime

from backend.video_summary.infrastructure.persistence.job_repository import JobSnapshot


def job_snapshot(
    *,
    id: str,
    workspace_id: str = "workspace-1",
    resource_type: str = "video",
    resource_id: str = "video-1",
    operation: str = "generate_summary",
    status: str = "running",
    started_at: datetime | None = None,
    failure_detail: str | None = None,
) -> JobSnapshot:
    return JobSnapshot(
        id=id,
        workspace_id=workspace_id,
        parent_job_id=None,
        resource_type=resource_type,
        resource_id=resource_id,
        operation=operation,
        status=status,
        attempt_count=1,
        max_attempts=3,
        cancel_requested=status == "cancelled",
        failure_code=None,
        failure_detail=failure_detail,
        result_content_version=None,
        started_at=started_at,
        finished_at=None,
    )
