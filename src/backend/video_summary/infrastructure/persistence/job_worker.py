"""Local or cloud worker host for durable summary-generation jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from threading import Event, Thread
from typing import Protocol
from uuid import uuid4
from backend.core.context import WorkspaceContext
from backend.core.request_context import bind_workspace_context
from backend.core.concurrency import RequestLimiter, bind_request_limiter, request_slot
from backend.video_summary.infrastructure.persistence.execution_context import bind_execution_claim, ContentVersionConflictError
from backend.video_summary.infrastructure.rag.agent_memory.api_models import ModelApiError

from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
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


@dataclass(frozen=True)
class WorkerOptions:
    worker_id: str
    operation_filter: frozenset[str] | None = None
    resource_class: str = "general"
    lease_seconds: int = 60
    heartbeat_seconds: int = 15
    poll_seconds: float = 0.25

    def __post_init__(self):
        if not self.worker_id.strip() or self.poll_seconds <= 0:
            raise ValueError("Worker identity and positive polling interval are required.")
        if not 0 < self.heartbeat_seconds < self.lease_seconds:
            raise ValueError("Worker heartbeat must be positive and shorter than the lease.")
        if self.operation_filter is not None and not self.operation_filter:
            raise ValueError("Worker operation filter must not be empty.")

    @classmethod
    def local(cls) -> "WorkerOptions":
        return cls(
            worker_id=f"local-{uuid4().hex}",
            operation_filter=frozenset({"generate_summary", "generate_transcript", "generate_series_batch", "generate_video_mindmap", "generate_series_mindmap", "generate_video_knowledge_cards", "generate_video_ai_summary", "download_linked_video", "process_agent_video", "import_chaoxing_course", "prepare_asr_model", "prepare_rag_model", "refresh_rag_index"}),
            resource_class="local-cpu",
            lease_seconds=120,
            heartbeat_seconds=20,
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
    ) -> None:
        self._repository = repository
        self._get_execution_services = get_execution_services
        self._options = options
        self._request_limiter = request_limiter
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name=f"vsummary-job-worker:{self._options.worker_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        self._thread = None

    def _run(self) -> None:
        with bind_request_limiter(self._request_limiter):
            while not self._stop.is_set():
                try:
                    with request_slot("jobs"):
                        if self._stop.is_set():
                            return
                        claim = self._repository.claim(worker_id=self._options.worker_id,
                            lease_seconds=self._options.lease_seconds, operations=self._options.operation_filter)
                        if claim is not None:
                            asyncio.run(self._execute(claim))
                    if claim is None:
                        self._stop.wait(self._options.poll_seconds)
                except JobLeaseLostError:
                    LOGGER.warning("worker execution lease was lost")
                except Exception:
                    LOGGER.exception("worker cycle failed")
                    self._stop.wait(self._options.poll_seconds)

    async def _execute(self, claim: ClaimedJob) -> None:
        identity = claim.request_payload.get("_execution_context", {})
        context = WorkspaceContext(workspace_id=claim.workspace_id,
            actor_id=identity.get("actor_id") or "system-worker", request_id=identity.get("request_id") or claim.id)
        with bind_execution_claim(claim), bind_workspace_context(context), bind_request_limiter(self._request_limiter):
            await self._execute_owned(claim)

    async def _execute_owned(self, claim: ClaimedJob) -> None:
        reporter = SqlJobProgressReporter(self._repository, claim)
        execution_task = asyncio.current_task()
        heartbeat = asyncio.create_task(self._heartbeat(claim, execution_task))
        try:
            reporter.raise_if_cancelled()
            services = self._get_execution_services(claim.workspace_id)
            handler = services.job_operation_handlers.get(claim.operation)
            if handler is not None:
                await handler(claim, reporter)
                self._repository.succeed(claim, detail="任务已完成")
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
                self._repository.succeed(claim, detail="生成内容已保存")
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
            self._repository.finalize_accounting(claim.id, workspace_id=claim.workspace_id)
            heartbeat.cancel()
            try:
                await heartbeat
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
