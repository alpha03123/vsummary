"""Local or cloud worker host for durable summary-generation jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from threading import Event, Lock, Thread
from typing import Protocol
from uuid import uuid4
from backend.core.context import WorkspaceContext
from backend.core.errors import UserVisibleError
from backend.core.request_context import bind_workspace_context
from backend.core.preferences import bind_user_preferences
from backend.core.metering import bind_resource_budget
from backend.core.concurrency import RequestLimiter, bind_request_limiter, request_slot
from backend.video_summary.infrastructure.persistence.execution_context import bind_execution_claim, ContentVersionConflictError
from backend.video_summary.infrastructure.rag.agent_memory.api_models import ModelApiError

from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError, _mirror_progress_cancellation
from backend.video_summary.generation.cancellation import GenerationCancellationContext, TaskHandle
from backend.video_summary.generation.errors import MediaSourceUnavailableError
from backend.video_summary.domain.models import ManualTranscriptInput
from backend.video_summary.infrastructure.subtitle_transcripts import parse_srt_transcript
from backend.video_summary.infrastructure.persistence.job_repository import (
    ClaimedJob,
    JobLeaseLostError,
    SqlJobRepository,
)
from backend.video_summary.infrastructure.persistence.sql_generation_adapters import SqlBackedVideoSummaryGenerator


LOGGER = logging.getLogger(__name__)


class JobExecutionServices(Protocol):
    """Workspace-owned dependencies used after a durable Job is claimed."""

    job_summary_generator: SqlBackedVideoSummaryGenerator
    job_operation_handlers: Mapping[str, Callable[[ClaimedJob, "SqlJobProgressReporter"], Awaitable[None]]]
    after_summary: Callable[[str,str], Awaitable[list[str]]] | None


@dataclass(frozen=True)
class WorkerOptions:
    worker_id: str
    operation_filter: frozenset[str] | None = None
    resource_class: str = "general"
    lease_seconds: int = 60
    heartbeat_seconds: int = 15
    poll_seconds: float = 0.25
    maintenance_seconds: float = 5
    concurrency: int = 1

    def __post_init__(self):
        if not self.worker_id.strip() or self.poll_seconds <= 0 or self.maintenance_seconds <= 0 or self.concurrency < 1:
            raise ValueError("Worker identity and positive polling interval are required.")
        if not 0 < self.heartbeat_seconds < self.lease_seconds:
            raise ValueError("Worker heartbeat must be positive and shorter than the lease.")
        if self.operation_filter is not None and not self.operation_filter:
            raise ValueError("Worker operation filter must not be empty.")

    @classmethod
    def local(cls, *, concurrency: int = 1) -> "WorkerOptions":
        return cls(
            worker_id=f"local-{uuid4().hex}",
            operation_filter=frozenset({"generate_summary", "generate_transcript", "generate_series_batch", "generate_video_mindmap", "generate_series_mindmap", "generate_video_knowledge_cards", "generate_video_ai_summary", "download_linked_video", "process_agent_video", "import_chaoxing_course", "prepare_asr_model", "prepare_rag_model", "refresh_rag_index"}),
            resource_class="local-cpu",
            lease_seconds=120,
            heartbeat_seconds=20,
            concurrency=concurrency,
        )


class SqlJobProgressReporter:
    """ProgressReporter adapter that persists events under a worker lease."""

    def __init__(self, repository: SqlJobRepository, claim: ClaimedJob) -> None:
        self._repository = repository
        self._claim = claim

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        self._repository.append_progress(self._claim, stage=stage, progress=progress, detail=detail)

    def completed(self, detail: str | None = None) -> None:
        self.update("complete", 100.0, detail)

    def failed(self, message: str) -> None:
        self.update("failed", None, message)

    def cancelled(self, detail: str | None = None) -> None:
        self._repository.append_progress(
            self._claim,
            stage="cancelled",
            progress=None,
            detail=detail,
            allow_cancelling=True,
        )

    def is_cancel_requested(self) -> bool:
        return self._repository.cancel_requested(self._claim)

    def raise_if_cancelled(self) -> None:
        if self.is_cancel_requested():
            raise GenerateCancelledError("Job cancellation was requested.")


class SqlJobWorker:
    """Polls the durable queue and executes the currently supported operations."""

    def __init__(
        self,
        *,
        repository: SqlJobRepository,
        get_execution_services: Callable[[str], JobExecutionServices],
        options: WorkerOptions,
        request_limiter: RequestLimiter | None = None,
        preference_store=None,
        model_profiles=None,
        resource_budget=None,
        maintenance=None,
    ) -> None:
        self._maintenance = maintenance
        self._repository = repository
        self._preference_store = preference_store
        self._model_profiles = model_profiles
        self._resource_budget = resource_budget
        self._get_execution_services = get_execution_services
        self._options = options
        self._request_limiter = request_limiter
        self._stop = Event()
        self._threads: dict[Thread, Event] = {}
        self._pool_lock = Lock()
        self._running = False
        self._worker_sequence = 0
        self._maintenance_thread: Thread | None = None

    @property
    def concurrency(self) -> int:
        return self._options.concurrency

    def start(self) -> None:
        with self._pool_lock:
            if self._running or any(thread.is_alive() for thread in self._threads):
                return
            self._stop.clear()
            self._running = True
            self._resize_threads()
            if self._maintenance is not None:
                self._maintenance_thread = Thread(target=self._run_maintenance,
                    name=f"vsummary-job-maintenance:{self._options.worker_id}", daemon=True)
                self._maintenance_thread.start()

    def update_concurrency(self, concurrency: int) -> None:
        with self._pool_lock:
            self._options = replace(self._options, concurrency=concurrency)
            if self._running:
                self._resize_threads()

    def _resize_threads(self) -> None:
        self._threads = {thread: retire for thread, retire in self._threads.items() if thread.is_alive()}
        active = [(thread, retire) for thread, retire in self._threads.items() if not retire.is_set()]
        for _, retire in active[self._options.concurrency:]:
            retire.set()
        for _ in range(self._options.concurrency - len(active)):
            self._worker_sequence += 1
            worker_id = f"{self._options.worker_id}-{self._worker_sequence}"
            retire = Event()
            thread = Thread(target=self._run, args=(worker_id, retire),
                name=f"vsummary-job-worker:{worker_id}", daemon=True)
            self._threads[thread] = retire
            thread.start()

    def stop(self) -> None:
        with self._pool_lock:
            self._running = False
            self._stop.set()
            threads = list(self._threads)
            for retire in self._threads.values():
                retire.set()
            maintenance = self._maintenance_thread
        for thread in threads:
            thread.join(timeout=5)
        if maintenance is not None:
            maintenance.join(timeout=5)
        with self._pool_lock:
            self._threads = {thread: retire for thread, retire in self._threads.items() if thread.is_alive()}
            if self._maintenance_thread is maintenance:
                self._maintenance_thread = None

    def _run_maintenance(self):
        while not self._stop.is_set():
            try:
                self._repository.retry_accounting()
                self._maintenance()
            except Exception:
                LOGGER.exception("worker maintenance failed")
            self._stop.wait(self._options.maintenance_seconds)

    def _run(self, worker_id: str, retire: Event) -> None:
        with bind_request_limiter(self._request_limiter):
            while not self._stop.is_set() and not retire.is_set():
                try:
                    with request_slot("jobs"):
                        if self._stop.is_set() or retire.is_set():
                            return
                        claim = self._repository.claim(worker_id=worker_id,
                            lease_seconds=self._options.lease_seconds, operations=self._options.operation_filter)
                        if claim is not None:
                            asyncio.run(self._execute(claim))
                        if self._maintenance is None:
                            self._repository.retry_accounting()
                    if claim is None:
                        retire.wait(self._options.poll_seconds)
                except JobLeaseLostError:
                    LOGGER.warning("worker execution lease was lost")
                except Exception:
                    LOGGER.exception("worker cycle failed")
                    retire.wait(self._options.poll_seconds)

    async def _execute(self, claim: ClaimedJob) -> None:
        identity = claim.request_payload.get("_execution_context", {})
        context = WorkspaceContext(workspace_id=claim.workspace_id,
            actor_id=identity.get("actor_id") or "system-worker", request_id=identity.get("request_id") or claim.id)
        preferences = claim.request_payload.get("_user_preferences")
        if preferences is None and self._preference_store is not None:
            preferences = self._preference_store.get(context)
        with bind_execution_claim(claim), bind_workspace_context(context), bind_request_limiter(self._request_limiter), bind_user_preferences(preferences, self._model_profiles), bind_resource_budget(self._resource_budget, claim.id):
            await self._execute_owned(claim)

    async def _execute_owned(self, claim: ClaimedJob) -> None:
        reporter = SqlJobProgressReporter(self._repository, claim)
        execution_task = asyncio.current_task()
        heartbeat = asyncio.create_task(self._heartbeat(claim, execution_task))
        cancellation = GenerationCancellationContext(claim.id)
        cancellation.register(TaskHandle(_task=execution_task))
        cancel_watcher = asyncio.create_task(_mirror_progress_cancellation(reporter, cancellation))
        try:
            reporter.raise_if_cancelled()
            services = self._get_execution_services(claim.workspace_id)
            handler = services.job_operation_handlers.get(claim.operation)
            if handler is not None:
                deferred = await handler(claim, reporter)
                if deferred is False:
                    return
                detail = "任务已完成"
                if (claim.operation == 'process_agent_video'
                    and claim.request_payload.get('processing_mode', 'summary') == 'summary'
                    and services.after_summary is not None):
                    failed=await services.after_summary(str(claim.request_payload['series_id']),claim.resource_id)
                    if failed:
                        reporter.update('auxiliary_failed',100,'视频已生成，部分附加产物生成失败。')
                        detail = "视频已生成；自动生成失败：" + ", ".join(failed)
                self._repository.succeed(claim, detail=detail)
                return
            if claim.operation not in {"generate_summary", "generate_transcript"}:
                self._repository.fail(
                    claim,
                    failure_code="invalid_request",
                    failure_detail=f"Unsupported job operation '{claim.operation}'.",
                    retry_delay_seconds=None,
                )
                return
            manual_transcript = _manual_transcript_from_payload(claim.request_payload)
            await services.job_summary_generator.run(
                series_id=str(claim.request_payload["series_id"]),
                video_id=claim.resource_id,
                processing_mode=str(claim.request_payload["processing_mode"]),
                transcript_enhancement_enabled=claim.request_payload.get("transcript_enhancement_enabled"),
                ai_summary_template=str(claim.request_payload.get("ai_summary_template") or "general"),
                manual_transcript=manual_transcript,
                use_saved_manual_transcript=bool(claim.request_payload.get("use_saved_manual_transcript", True)),
                progress_reporter=reporter,
                job_id=claim.id,
                worker_id=claim.worker_id,
                lease_token=claim.lease_token,
            )
            snapshot = self._repository.get(claim.id)
            if snapshot is None:
                raise JobLeaseLostError("Job disappeared after execution.")
            if snapshot.status == "running" and snapshot.result_content_version is not None:
                detail = "生成内容已保存"
                if claim.operation=='generate_summary' and services.after_summary is not None:
                    failed=await services.after_summary(str(claim.request_payload['series_id']),claim.resource_id)
                    if failed:
                        reporter.update('auxiliary_failed',100,'视频已生成，部分附加产物生成失败。')
                        detail = "生成内容已保存；自动生成失败：" + ", ".join(failed)
                self._repository.succeed(claim, detail=detail)
            elif snapshot.status != "succeeded":
                if snapshot.cancel_requested:
                    self._repository.mark_cancelled(claim, detail="任务已取消，未发布候选内容")
                else:
                    self._repository.fail(
                        claim,
                        failure_code="internal_error",
                        failure_detail="Generation completed without publishing content.",
                        retry_delay_seconds=None,
                    )
        except asyncio.CancelledError:
            # A heartbeat failure cancels async work. Synchronous work can finish,
            # but its persistence calls still verify the lease transactionally.
            if reporter.is_cancel_requested():
                self._repository.mark_cancelled(claim, detail="任务已取消")
                return
            raise JobLeaseLostError("Worker execution was interrupted by lease loss.")
        except GenerateCancelledError:
            self._repository.mark_cancelled(claim, detail="任务已取消，未发布候选内容")
        except JobLeaseLostError:
            if reporter.is_cancel_requested():
                self._repository.mark_cancelled(claim, detail="任务已取消")
                return
            raise
        except Exception as error:
            if reporter.is_cancel_requested():
                self._repository.mark_cancelled(claim, detail="任务已取消")
                return
            LOGGER.exception("job execution failed", extra={"job_id": claim.id, "workspace_id": claim.workspace_id})
            self._repository.fail(
                claim,
                failure_code=_failure_code(error),
                failure_detail=_public_failure_detail(error),
                retry_delay_seconds=_retry_delay_seconds(error),
            )
        finally:
            try:
                self._repository.finalize_accounting(claim.id, workspace_id=claim.workspace_id)
                snapshot = self._repository.get(claim.id, workspace_id=claim.workspace_id)
                if snapshot is not None and snapshot.parent_job_id is not None:
                    self._repository.finalize_accounting(snapshot.parent_job_id, workspace_id=claim.workspace_id)
            finally:
                heartbeat.cancel()
                cancel_watcher.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                try:
                    await cancel_watcher
                except asyncio.CancelledError:
                    pass

    async def _heartbeat(self, claim: ClaimedJob, execution_task: asyncio.Task) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self._options.heartbeat_seconds)
            try:
                await asyncio.to_thread(
                    self._repository.renew_lease,
                    claim,
                    lease_seconds=self._options.lease_seconds,
                )
            except JobLeaseLostError:
                execution_task.cancel()
                return
            except Exception:
                LOGGER.exception("job %s heartbeat failed", claim.id)
                execution_task.cancel()
                return


def _failure_code(error: Exception) -> str:
    if isinstance(error, UserVisibleError):
        return error.code
    if isinstance(error, MediaSourceUnavailableError):
        return "media_source_unavailable"
    if isinstance(error, ContentVersionConflictError):
        return "content_conflict"
    if isinstance(error, ModelApiError):
        return error.code
    if isinstance(error, (ValueError, LookupError)):
        return "invalid_request"
    if isinstance(error, (TimeoutError, ConnectionError, OSError)) or getattr(error, "status_code", 0) in {429, 500, 502, 503, 504}:
        return "provider_unavailable"
    return "internal_error"


def _public_failure_detail(error: Exception) -> str:
    if isinstance(error, UserVisibleError):
        return str(error)
    if isinstance(error, MediaSourceUnavailableError):
        return str(error)
    code = _failure_code(error)
    if code == "content_conflict":
        return "生成期间内容已修改，请基于最新内容重新提交。"
    if code == "invalid_request":
        return "任务参数或目标资源无效。"
    if code.startswith("provider_"):
        return "模型服务请求失败，请查看任务错误码或服务器日志。"
    return "任务执行失败，请查看服务器日志。"


def _retry_delay_seconds(error: Exception) -> int | None:
    if isinstance(error, ModelApiError):
        return int(error.retry_after or 15) if error.retryable else None
    return 15 if isinstance(error, (TimeoutError, ConnectionError, OSError)) or getattr(error, "status_code", 0) in {429, 500, 502, 503, 504} else None


def _manual_transcript_from_payload(payload: dict[str, object]) -> ManualTranscriptInput | None:
    value = payload.get("manual_transcript")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("manual_transcript payload must be an object.")
    raw_srt = value.get("raw_srt")
    filename = value.get("filename")
    if not isinstance(raw_srt, str) or not isinstance(filename, str):
        raise ValueError("manual_transcript payload is invalid.")
    return ManualTranscriptInput(
        transcript=parse_srt_transcript(raw_srt),
        raw_srt=raw_srt,
        filename=filename,
    )
