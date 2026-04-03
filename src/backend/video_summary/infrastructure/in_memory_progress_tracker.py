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
        with self._lock:
            self._cancelled_tasks.discard(task_id)
            self._snapshots[task_id] = ProgressSnapshot(
                status="running",
                stage="prepare",
                progress=0.0,
                detail="任务已开始",
                error=None,
                sequence=0,
                updated_at=time.time(),
            )
        return TaskProgressReporter(self, task_id)

    def get_snapshot(self, task_id: str) -> ProgressSnapshot:
        with self._lock:
            return self._snapshots.get(
                task_id,
                ProgressSnapshot(
                    status="idle",
                    stage=None,
                    progress=None,
                    detail=None,
                    error=None,
                    sequence=0,
                    updated_at=time.time(),
                ),
            )

    def request_cancel(self, task_id: str) -> None:
        with self._lock:
            self._cancelled_tasks.add(task_id)
            previous = self._snapshots.get(task_id)
            sequence = 0 if previous is None else previous.sequence + 1
            self._snapshots[task_id] = ProgressSnapshot(
                status="cancelled",
                stage="cancelled",
                progress=previous.progress if previous is not None else None,
                detail="任务已取消",
                error=None,
                sequence=sequence,
                updated_at=time.time(),
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
        with self._lock:
            previous = self._snapshots.get(task_id)
            sequence = 0 if previous is None else previous.sequence + 1
            normalized_progress = None if progress is None else max(0.0, min(100.0, progress))
            self._snapshots[task_id] = ProgressSnapshot(
                status=status,
                stage=stage,
                progress=normalized_progress,
                detail=detail,
                error=error,
                sequence=sequence,
                updated_at=time.time(),
            )


class TaskProgressReporter:
    def __init__(self, tracker: InMemoryProgressTracker, task_id: str) -> None:
        self._tracker = tracker
        self._task_id = task_id

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
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
