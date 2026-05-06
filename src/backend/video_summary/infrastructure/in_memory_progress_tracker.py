from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProgressSnapshot:
    status: str
    stage: str | None
    progress: float | None
    detail: str | None
    error: str | None
    started_at: float
    stage_started_at: float | None
    elapsed_seconds: float
    stage_elapsed_seconds: float | None
    estimated_total_seconds: float | None
    remaining_seconds: float | None
    sequence: int
    updated_at: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class InMemoryProgressTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshots: dict[str, ProgressSnapshot] = {}
        self._cancelled_tasks: set[str] = set()

    def create_reporter(self, task_id: str) -> "TaskProgressReporter":
        now = time.time()
        with self._lock:
            previous = self._snapshots.get(task_id)
            sequence = 0 if previous is None else previous.sequence + 1
            self._cancelled_tasks.discard(task_id)
            self._snapshots[task_id] = ProgressSnapshot(
                status="running",
                stage="prepare",
                progress=0.0,
                detail="任务已开始",
                error=None,
                started_at=now,
                stage_started_at=now,
                elapsed_seconds=0.0,
                stage_elapsed_seconds=0.0,
                estimated_total_seconds=None,
                remaining_seconds=None,
                sequence=sequence,
                updated_at=now,
            )
        return TaskProgressReporter(self, task_id)

    def get_snapshot(self, task_id: str) -> ProgressSnapshot:
        now = time.time()
        with self._lock:
            snapshot = self._snapshots.get(task_id)
            if snapshot is None:
                snapshot = ProgressSnapshot(
                    status="idle",
                    stage=None,
                    progress=None,
                    detail=None,
                    error=None,
                    started_at=now,
                    stage_started_at=None,
                    elapsed_seconds=0.0,
                    stage_elapsed_seconds=None,
                    estimated_total_seconds=None,
                    remaining_seconds=None,
                    sequence=0,
                    updated_at=now,
                )
                self._snapshots[task_id] = snapshot
            return snapshot

    def request_cancel(self, task_id: str) -> None:
        now = time.time()
        with self._lock:
            self._cancelled_tasks.add(task_id)
            previous = self._snapshots.get(task_id)
            sequence = 0 if previous is None else previous.sequence + 1
            self._snapshots[task_id] = ProgressSnapshot(
                status="cancelling",
                stage="cancelling",
                progress=previous.progress if previous is not None else None,
                detail="正在取消任务",
                error=None,
                started_at=now if previous is None else previous.started_at,
                stage_started_at=now,
                elapsed_seconds=0.0 if previous is None else max(0.0, now - previous.started_at),
                stage_elapsed_seconds=0.0,
                estimated_total_seconds=(
                    None
                    if previous is None
                    else _estimate_total_seconds(
                        elapsed_seconds=max(0.0, now - previous.started_at),
                        progress=previous.progress,
                        status="cancelling",
                    )
                ),
                remaining_seconds=None,
                sequence=sequence,
                updated_at=now,
            )

    def is_cancel_requested(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._cancelled_tasks

    def _write(
        self,
        task_id: str,
        *,
        status: str,
        stage: str | None,
        progress: float | None,
        detail: str | None,
        error: str | None,
    ) -> None:
        now = time.time()
        with self._lock:
            previous = self._snapshots.get(task_id)
            sequence = 0 if previous is None else previous.sequence + 1
            normalized_progress = None if progress is None else max(0.0, min(100.0, progress))
            started_at = now if previous is None else previous.started_at
            stage_started_at = _resolve_stage_started_at(previous, stage, now)
            elapsed_seconds = max(0.0, now - started_at)
            stage_elapsed_seconds = (
                None if stage_started_at is None else max(0.0, now - stage_started_at)
            )
            estimated_total_seconds = _estimate_total_seconds(
                elapsed_seconds=elapsed_seconds,
                progress=normalized_progress,
                status=status,
            )
            remaining_seconds = _estimate_remaining_seconds(
                elapsed_seconds=elapsed_seconds,
                estimated_total_seconds=estimated_total_seconds,
                status=status,
            )
            self._snapshots[task_id] = ProgressSnapshot(
                status=status,
                stage=stage,
                progress=normalized_progress,
                detail=detail,
                error=error,
                started_at=started_at,
                stage_started_at=stage_started_at,
                elapsed_seconds=elapsed_seconds,
                stage_elapsed_seconds=stage_elapsed_seconds,
                estimated_total_seconds=estimated_total_seconds,
                remaining_seconds=remaining_seconds,
                sequence=sequence,
                updated_at=now,
            )


class TaskProgressReporter:
    def __init__(self, tracker: InMemoryProgressTracker, task_id: str) -> None:
        self._tracker = tracker
        self._task_id = task_id

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        if self.is_cancel_requested():
            return
        self._tracker._write(
            self._task_id,
            status="running",
            stage=stage,
            progress=progress,
            detail=detail,
            error=None,
        )

    def completed(self, detail: str | None = None) -> None:
        self._tracker._write(
            self._task_id,
            status="completed",
            stage="completed",
            progress=100.0,
            detail=detail,
            error=None,
        )

    def failed(self, message: str) -> None:
        self._tracker._write(
            self._task_id,
            status="failed",
            stage="failed",
            progress=None,
            detail=None,
            error=message,
        )

    def cancelled(self, detail: str | None = None) -> None:
        self._tracker._write(
            self._task_id,
            status="cancelled",
            stage="cancelled",
            progress=None,
            detail=detail or "任务已取消",
            error=None,
        )

    def is_cancel_requested(self) -> bool:
        return self._tracker.is_cancel_requested(self._task_id)

    def raise_if_cancelled(self) -> None:
        if self.is_cancel_requested():
            raise RuntimeError("下载已取消")


def _resolve_stage_started_at(
    previous: ProgressSnapshot | None,
    stage: str | None,
    now: float,
) -> float | None:
    if stage is None:
        return None
    if previous is None:
        return now
    if previous.stage == stage and previous.stage_started_at is not None:
        return previous.stage_started_at
    return now


def _estimate_total_seconds(
    *,
    elapsed_seconds: float,
    progress: float | None,
    status: str,
) -> float | None:
    if status == "completed":
        return elapsed_seconds
    if progress is None or progress <= 0.0:
        return None
    return elapsed_seconds / (progress / 100.0)


def _estimate_remaining_seconds(
    *,
    elapsed_seconds: float,
    estimated_total_seconds: float | None,
    status: str,
) -> float | None:
    if status in {"completed", "cancelled"}:
        return 0.0
    if estimated_total_seconds is None:
        return None
    return max(0.0, estimated_total_seconds - elapsed_seconds)
