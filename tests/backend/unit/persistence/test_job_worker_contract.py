from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.video_summary.infrastructure.persistence.job_repository import ClaimedJob
from backend.video_summary.infrastructure.persistence.job_worker import SqlJobProgressReporter, SqlJobWorker, WorkerOptions


class _Repository:
    def __init__(self) -> None:
        self.succeeded: list[str] = []
        self.failed: list[str] = []

    def cancel_requested(self, _claim) -> bool:
        return False

    def append_progress(self, *_args, **_kwargs) -> None:
        return None

    def succeed(self, claim, *, detail: str) -> None:
        self.succeeded.append(detail)

    def fail(self, _claim, **_kwargs) -> None:
        self.failed.append("failed")


class JobWorkerContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_custom_operation_handler_is_confirmed_through_durable_success(self) -> None:
        repository = _Repository()
        called: list[str] = []

        async def handler(claim, reporter) -> None:
            called.append(claim.operation)
            reporter.update("generate", 50.0, "working")

        worker = SqlJobWorker(
            repository=repository,
            summary_generator=SimpleNamespace(),
            operation_handlers={"custom": handler},
            options=WorkerOptions(worker_id="worker", operation_filter=frozenset({"custom"})),
        )
        claim = ClaimedJob(
            id="job", workspace_id="workspace", resource_type="video", resource_id="video", operation="custom",
            request_payload={}, attempt_no=1, worker_id="worker", lease_token="token", lease_expires_at=datetime.now(timezone.utc),
        )

        await worker._execute(claim)

        self.assertEqual(called, ["custom"])
        self.assertEqual(repository.succeeded, ["任务已完成"])
        self.assertEqual(repository.failed, [])
