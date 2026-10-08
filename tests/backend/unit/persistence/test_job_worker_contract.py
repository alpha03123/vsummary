from __future__ import annotations

from tests._api_fixtures import make_workspace_services

import unittest
from datetime import datetime, timezone
import asyncio
from queue import Empty, Queue
from threading import Event
from types import SimpleNamespace

import pytest

from backend.video_summary.infrastructure.persistence.job_repository import ClaimedJob
from backend.video_summary.infrastructure.persistence.job_worker import SqlJobWorker, WorkerOptions


class _Repository:
    def get(self,*args,**kwargs):
        return None
    def cancel_requested(self, _claim) -> bool:
        self.cancel_checks += 1
        return self.cancelled and self.cancel_checks >= self.cancel_on_check

    def append_progress(self, *_args, **_kwargs) -> None:
        return None

    def succeed(self, claim, *, detail: str) -> None:
        self.succeeded.append(detail)

    def fail(self, _claim, **_kwargs) -> None:
        self.failed.append("failed")

    def mark_cancelled(self, _claim, *, detail: str) -> None:
        self.cancelled_details.append(detail)

    def finalize_accounting(self, _job_id, *, workspace_id: str) -> None:
        self.accounting_workspaces.append(workspace_id)

    def __init__(self, *, cancelled: bool = False, cancel_on_check: int = 1) -> None:
        self.succeeded: list[str] = []
        self.failed: list[str] = []
        self.cancelled = cancelled
        self.cancel_on_check = cancel_on_check
        self.cancel_checks = 0
        self.cancelled_details: list[str] = []
        self.accounting_workspaces: list[str] = []


class JobWorkerContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_handler_stops_waiting_when_cancel_requested(self):
        import asyncio
        repository=_Repository(cancelled=True,cancel_on_check=2)
        interrupted=[]
        async def handler(_claim,_reporter):
            try:await asyncio.sleep(60)
            except asyncio.CancelledError:
                interrupted.append(True);raise
        worker=SqlJobWorker(repository=repository,
            get_execution_services=lambda _:make_workspace_services(job_operation_handlers={'custom':handler}),
            options=WorkerOptions(worker_id='worker',operation_filter=frozenset({'custom'})))
        claim=ClaimedJob(id='job',workspace_id='workspace',resource_type='video',resource_id='video',operation='custom',
            request_payload={},attempt_no=1,worker_id='worker',lease_token='token',lease_expires_at=datetime.now(timezone.utc))
        await asyncio.wait_for(worker._execute(claim),0.5)
        self.assertEqual(interrupted,[True])
        self.assertTrue(repository.cancelled_details)
        self.assertEqual(repository.succeeded,[])

    async def test_custom_operation_handler_is_confirmed_through_durable_success(self) -> None:
        repository = _Repository()
        called: list[str] = []

        async def handler(claim, reporter) -> None:
            called.append(claim.operation)
            reporter.update("generate", 50.0, "working")

        resolved_workspaces: list[str] = []
        worker = SqlJobWorker(
            repository=repository,
            get_execution_services=lambda workspace_id: (
                resolved_workspaces.append(workspace_id)
                or make_workspace_services(job_operation_handlers={"custom": handler})
            ),
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
        self.assertEqual(repository.accounting_workspaces, ["workspace"])
        self.assertEqual(resolved_workspaces, ["workspace"])

    async def test_custom_handler_exception_becomes_cancelled_when_job_was_cancelled(self) -> None:
        repository = _Repository(cancelled=True, cancel_on_check=2)

        async def handler(_claim, _reporter) -> None:
            raise RuntimeError("provider aborted after cancellation")

        worker = SqlJobWorker(
            repository=repository,
            get_execution_services=lambda _workspace_id: make_workspace_services(job_operation_handlers={"custom": handler}),
            options=WorkerOptions(worker_id="worker", operation_filter=frozenset({"custom"})),
        )
        claim = ClaimedJob(
            id="job", workspace_id="workspace", resource_type="model", resource_id="model", operation="custom",
            request_payload={}, attempt_no=1, worker_id="worker", lease_token="token", lease_expires_at=datetime.now(timezone.utc),
        )

        await worker._execute(claim)

        self.assertEqual(repository.cancelled_details, ["任务已取消"])
        self.assertEqual(repository.failed, [])


class _QueuedRepository(_Repository):
    def __init__(self, count):
        super().__init__()
        self.pending = Queue()
        self.completed = Queue()
        for index in range(count):
            self.pending.put(str(index))

    def claim(self, *, worker_id, **_kwargs):
        try:
            job_id = self.pending.get_nowait()
        except Empty:
            return None
        return ClaimedJob(
            id=job_id, workspace_id="workspace", resource_type="video", resource_id=job_id,
            operation="custom", request_payload={}, attempt_no=1, worker_id=worker_id,
            lease_token=job_id, lease_expires_at=datetime.now(timezone.utc),
        )

    def succeed(self, claim, *, detail):
        super().succeed(claim, detail=detail)
        self.completed.put(claim.id)

    def retry_accounting(self):
        pass


def _queued_worker(count, concurrency):
    repository = _QueuedRepository(count)
    entered = Queue()
    releases = {str(index): Event() for index in range(count)}

    async def handler(claim, _reporter):
        entered.put((claim.id, claim.worker_id))
        await asyncio.to_thread(releases[claim.id].wait, 5)

    worker = SqlJobWorker(
        repository=repository,
        get_execution_services=lambda _: SimpleNamespace(job_operation_handlers={"custom": handler}),
        options=WorkerOptions(worker_id="queue-test", concurrency=concurrency,
            operation_filter=frozenset({"custom"}), poll_seconds=.01),
    )
    return worker, repository, entered, releases


def test_fixed_worker_concurrency_limits_claims_until_a_slot_is_free():
    worker, repository, entered, releases = _queued_worker(3, 2)
    worker.start()
    try:
        first = entered.get(timeout=2)[0]
        second = entered.get(timeout=2)[0]
        with pytest.raises(Empty):
            entered.get(timeout=.1)
        releases[first].set()
        third = entered.get(timeout=2)[0]
        assert len({first, second, third}) == 3
    finally:
        for release in releases.values():
            release.set()
        worker.stop()
    assert len(repository.succeeded) == 3
    assert repository.failed == []


def test_worker_resize_grows_immediately_and_retires_after_running_jobs_finish():
    worker, repository, entered, releases = _queued_worker(5, 1)
    worker.start()
    try:
        first = entered.get(timeout=2)[0]
        worker.update_concurrency(3)
        retiring = [entered.get(timeout=2), entered.get(timeout=2)]
        worker.update_concurrency(1)
        for job_id, _ in retiring:
            releases[job_id].set()
        assert {repository.completed.get(timeout=2), repository.completed.get(timeout=2)} == {
            job_id for job_id, _ in retiring
        }
        with pytest.raises(Empty):
            entered.get(timeout=.1)
        releases[first].set()
        fourth, fourth_worker = entered.get(timeout=2)
        worker.update_concurrency(2)
        fifth, fifth_worker = entered.get(timeout=2)
        assert fourth != fifth
        assert fifth_worker not in {worker_id for _, worker_id in retiring} | {fourth_worker}
        assert worker.concurrency == 2
    finally:
        for release in releases.values():
            release.set()
        worker.stop()
    assert len(repository.succeeded) == 5
    assert repository.failed == []
    assert repository.cancelled_details == []
