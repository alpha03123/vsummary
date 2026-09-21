"""Local or cloud worker host for durable summary-generation jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import Event, Thread
from uuid import uuid4

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


@dataclass(frozen=True)
class WorkerOptions:
    worker_id: str
    operation_filter: frozenset[str] | None = None
    resource_class: str = "general"
    lease_seconds: int = 60
    heartbeat_seconds: int = 15
    poll_seconds: float = 0.25

    @classmethod
    def local(cls) -> "WorkerOptions":
        return cls(
            worker_id=f"local-{uuid4().hex}",
            operation_filter=frozenset({"generate_summary", "generate_transcript", "generate_video_mindmap", "generate_series_mindmap", "generate_video_knowledge_cards", "generate_video_ai_summary"}),
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
        self.update("cancelled", None, detail)

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
        summary_generator: SqlBackedVideoSummaryGenerator,
        operation_handlers: dict[str, Callable[[ClaimedJob, SqlJobProgressReporter], Awaitable[None]]] | None = None,
        options: WorkerOptions,
    ) -> None:
        self._repository = repository
        self._summary_generator = summary_generator
        self._operation_handlers = operation_handlers or {}
        self._options = options
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
        while not self._stop.is_set():
            try:
                claim = self._repository.claim(
                    worker_id=self._options.worker_id,
                    lease_seconds=self._options.lease_seconds,
                    operations=self._options.operation_filter,
                )
            except Exception:
                LOGGER.exception("job claim failed")
                self._stop.wait(self._options.poll_seconds)
                continue
            if claim is None:
                self._stop.wait(self._options.poll_seconds)
                continue
            try:
                asyncio.run(self._execute(claim))
            except JobLeaseLostError:
                LOGGER.warning("job %s lease was lost before the worker could finish", claim.id)
            except Exception:
                LOGGER.exception("job %s escaped worker error handling", claim.id)

    async def _execute(self, claim: ClaimedJob) -> None:
        reporter = SqlJobProgressReporter(self._repository, claim)
        heartbeat = asyncio.create_task(self._heartbeat(claim))
        try:
            reporter.raise_if_cancelled()
            handler = self._operation_handlers.get(claim.operation)
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
            await self._summary_generator.run(
                series_id=str(claim.request_payload["series_id"]),
                video_id=claim.resource_id,
                processing_mode=str(claim.request_payload["processing_mode"]),
                transcript_enhancement_enabled=claim.request_payload.get("transcript_enhancement_enabled"),
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
            if snapshot.status != "succeeded":
                if snapshot.cancel_requested:
                    self._repository.mark_cancelled(claim, detail="任务已取消，未发布候选内容")
                else:
                    self._repository.fail(
                        claim,
                        failure_code="internal_error",
                        failure_detail="Generation completed without publishing content.",
                        retry_delay_seconds=None,
                    )
        except GenerateCancelledError:
            self._repository.mark_cancelled(claim, detail="任务已取消，未发布候选内容")
        except JobLeaseLostError:
            raise
        except Exception as error:
            self._repository.fail(
                claim,
                failure_code=_failure_code(error),
                failure_detail=str(error),
                retry_delay_seconds=_retry_delay_seconds(error),
            )
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self, claim: ClaimedJob) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self._options.heartbeat_seconds)
            try:
                await asyncio.to_thread(
                    self._repository.renew_lease,
                    claim,
                    lease_seconds=self._options.lease_seconds,
                )
            except JobLeaseLostError:
                return
            except Exception:
                LOGGER.exception("job %s heartbeat failed", claim.id)
                return


def _failure_code(error: Exception) -> str:
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return "provider_unavailable"
    return "internal_error"


def _retry_delay_seconds(error: Exception) -> int | None:
    return 15 if isinstance(error, (TimeoutError, ConnectionError, OSError)) else None


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
