from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.video_summary.infrastructure.persistence.job_repository import ClaimedJob
from backend.video_summary.infrastructure.persistence.job_worker import SqlJobProgressReporter, SqlJobWorker, WorkerOptions


class _Repository:
    def cancel_requested(self, _claim) -> bool:
        self.cancel_checks += 1
        return self.cancelled and self.cancel_checks >= self.cancel_on_check

    def append_progress(self, *_args, **_kwargs) -> None:
        return None

    def get(self, _job_id, *, workspace_id):
        del workspace_id
        return SimpleNamespace(status="running")

    def succeed(self, claim, *, detail: str) -> None:
        self.succeeded.append(detail)

    def fail(self, _claim, **_kwargs) -> None:
        self.failed.append("failed")

    def mark_cancelled(self, _claim, *, detail: str) -> None:
        self.cancelled_details.append(detail)

    def __init__(self, *, cancelled: bool = False, cancel_on_check: int = 1) -> None:
        self.succeeded: list[str] = []
        self.failed: list[str] = []
        self.cancelled = cancelled
        self.cancel_on_check = cancel_on_check
        self.cancel_checks = 0
        self.cancelled_details: list[str] = []


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

    async def test_custom_handler_exception_becomes_cancelled_when_job_was_cancelled(self) -> None:
        repository = _Repository(cancelled=True, cancel_on_check=2)

        async def handler(_claim, _reporter) -> None:
            raise RuntimeError("provider aborted after cancellation")

        worker = SqlJobWorker(
            repository=repository,
            summary_generator=SimpleNamespace(),
            operation_handlers={"custom": handler},
            options=WorkerOptions(worker_id="worker", operation_filter=frozenset({"custom"})),
        )
        claim = ClaimedJob(
            id="job", workspace_id="workspace", resource_type="model", resource_id="model", operation="custom",
            request_payload={}, attempt_no=1, worker_id="worker", lease_token="token", lease_expires_at=datetime.now(timezone.utc),
        )

        await worker._execute(claim)

        self.assertEqual(repository.cancelled_details, ["任务已取消"])
        self.assertEqual(repository.failed, [])

    async def test_custom_handler_that_publishes_content_is_not_finished_twice(self) -> None:
        repository = _Repository()
        repository.get = lambda _job_id, *, workspace_id: SimpleNamespace(status="succeeded")

        async def handler(_claim, _reporter) -> None:
            return None

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

        self.assertEqual(repository.succeeded, [])
