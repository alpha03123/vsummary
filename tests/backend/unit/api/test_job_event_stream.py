from tests._job_fixtures import job_snapshot

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

from backend.api.routes.jobs import stream_job_events
from backend.core.context import WorkspaceContext
from backend.video_summary.infrastructure.persistence.job_repository import JobEventSnapshot


def test_stream_does_not_drop_completion_when_job_finishes_between_reads():
    now = datetime.now(timezone.utc)
    repository = Mock()
    # 校验请求、首轮取事件前、下一轮取事件前。
    repository.get.side_effect = [job_snapshot(id="job-1", status=status) for status in ["running", "running", "succeeded"]]
    repository.events.side_effect = [
        [JobEventSnapshot(sequence=1, status="running", stage="understand_frames", progress=None,
                          detail="Reading pictures", occurred_at=now, started_at=now)],
        [JobEventSnapshot(sequence=2, status="succeeded", stage="succeeded", progress=100,
                          detail="Done", occurred_at=now, started_at=now)],
    ]
    async def collect():
        response = await stream_job_events("job-1", repository, WorkspaceContext("workspace-1", "actor-1", "request-1"))
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(collect())
    assert len(chunks) == 2
    assert '"status": "succeeded"' in chunks[-1]
    assert repository.events.call_args_list[-1].kwargs["after_sequence"] == 1
