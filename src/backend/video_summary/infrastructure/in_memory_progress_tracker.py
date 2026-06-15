"""基于内存的进度跟踪与 SSE 上报支撑。

提供：
- `InMemoryProgressTracker`：任务维度的进度状态机，按 `task_id` 持有最新
  `ProgressSnapshot`，并对外暴露 `request_cancel` / `is_cancel_requested`；
- `TaskProgressReporter`：每个任务一份的 reporter，调用方可在任意位置
  派发 `update / completed / failed / cancelled` 事件；
- `ProgressSnapshot`：前端 SSE 消费的不变快照（含状态、阶段、百分比、
  已耗时、剩余时间估算、序列号等）。

线程安全：所有读写都通过 `_lock`（`threading.Lock`）串行化。
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProgressSnapshot:
    """单个任务在某一时刻的进度快照（不可变）。

    Attributes:
        status: 任务状态，取值 `idle` / `running` / `cancelling` / `cancelled`
            / `completed` / `failed`。
        stage: 当前阶段名（业务自定义，如 `download` / `transcribe`）。
        progress: 进度百分比，区间 `[0, 100]`，未开始时为 `None`。
        detail: 人类可读的描述文本。
        error: 失败原因消息；非 `failed` 状态时为 `None`。
        started_at: 任务首次创建的时间戳（秒）。
        stage_started_at: 当前阶段开始的时间戳；阶段未启动时为 `None`。
        elapsed_seconds: 距 `started_at` 的已耗时。
        stage_elapsed_seconds: 距 `stage_started_at` 的本阶段耗时。
        estimated_total_seconds: 按当前进度估算的总耗时；无法估算时为 `None`。
        remaining_seconds: 估算的剩余耗时；无法估算时为 `None`，终态时为 `0.0`。
        sequence: 每次写操作自增的序号，前端可据此识别"是否漏掉了中间帧"。
        updated_at: 本次快照写入的时间戳。
    """

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
        """把不可变快照转换为 dict，便于 JSON 序列化到 SSE。"""
        return asdict(self)


class InMemoryProgressTracker:
    """按 `task_id` 维护进度状态、取消请求与 reporter 工厂。

    设计要点：
    - 同一 `task_id` 可被 `create_reporter` 多次调用，每次创建 reporter 都会
      视作"新一轮开始"，并把 sequence 递增；
    - `request_cancel` 把任务标记为 `cancelling`，后续由 reporter 在确认后切到
      `cancelled`；状态机对部分"非合法跃迁"做了写保护（见 `_BLOCKED_WRITES`）。
    """

    def __init__(self) -> None:
        """初始化内存存储与线程锁。"""
        self._lock = threading.Lock()
        self._snapshots: dict[str, ProgressSnapshot] = {}
        self._cancelled_tasks: set[str] = set()

    def create_reporter(self, task_id: str) -> "TaskProgressReporter":
        """为指定任务创建一个新的 reporter 并把快照初始化为 `running`。

        副作用：清除先前的取消标记，保证新一次任务可以正常推进。

        Args:
            task_id: 任务唯一标识。

        Returns:
            绑定到该 `task_id` 的 `TaskProgressReporter` 实例。
        """
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
        """读取任务的当前快照；若不存在则返回 `idle` 占位快照并缓存下来。"""
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
        """请求取消指定任务：写入 `cancelling` 状态并打上取消标记。

        实际的下游取消由 reporter 在合适时机调用 `cancelled()` 完成。
        """
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
        """判断指定任务是否已被请求取消（与具体快照状态解耦）。"""
        with self._lock:
            return task_id in self._cancelled_tasks

    _TERMINAL_STATES = frozenset({"cancelled", "completed", "failed"})
    _BLOCKED_WRITES: dict[str, frozenset[str]] = {
        "cancelling": frozenset({"completed", "running"}),
        "cancelled": frozenset({"completed", "running"}),
        "completed": frozenset({"cancelled"}),
    }

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
        """把一次进度事件写入快照：包含状态机校验、进度归一化、时间字段更新。

        写入规则：
        - 受 `_BLOCKED_WRITES` 保护的部分跃迁会被静默丢弃，避免
          `cancelled → completed` 这类竞态；
        - `progress` 被钳制到 `[0, 100]`；
        - 自动维护 `elapsed_seconds` / `stage_elapsed_seconds` /
          `estimated_total_seconds` / `remaining_seconds`。
        """
        now = time.time()
        with self._lock:
            previous = self._snapshots.get(task_id)
            if previous is not None and status in self._BLOCKED_WRITES.get(previous.status, frozenset()):
                return
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
    """绑定到 `task_id` 的进度 reporter，对外暴露"业务级"事件。"""

    def __init__(self, tracker: InMemoryProgressTracker, task_id: str) -> None:
        """注入 tracker 与目标 `task_id`。"""
        self._tracker = tracker
        self._task_id = task_id

    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None:
        """上报一次进度更新；若任务已被请求取消则会被静默忽略。

        Args:
            stage: 当前阶段名（如 `download` / `transcribe`）。
            progress: 进度百分比，区间 `[0, 100]`；不更新时传 `None`。
            detail: 人类可读的描述文本。
        """
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
        """把任务标记为已完成，进度归 100%。"""
        self._tracker._write(
            self._task_id,
            status="completed",
            stage="completed",
            progress=100.0,
            detail=detail,
            error=None,
        )

    def failed(self, message: str) -> None:
        """把任务标记为失败，记录 `error` 字段。"""
        self._tracker._write(
            self._task_id,
            status="failed",
            stage="failed",
            progress=None,
            detail=None,
            error=message,
        )

    def cancelled(self, detail: str | None = None) -> None:
        """把任务标记为已取消，detail 默认为 `"任务已取消"`。"""
        self._tracker._write(
            self._task_id,
            status="cancelled",
            stage="cancelled",
            progress=None,
            detail=detail or "任务已取消",
            error=None,
        )

    def is_cancel_requested(self) -> bool:
        """查询当前任务是否已被请求取消（始终查询最新状态）。"""
        return self._tracker.is_cancel_requested(self._task_id)

    def raise_if_cancelled(self) -> None:
        """若已请求取消则抛 `RuntimeError("任务已取消")`，便于在长循环里点检。"""
        if self.is_cancel_requested():
            raise RuntimeError("任务已取消")


def _resolve_stage_started_at(
    previous: ProgressSnapshot | None,
    stage: str | None,
    now: float,
) -> float | None:
    """根据前一快照与当前 stage 计算"当前阶段的开始时间"。

    规则：同一 stage 连续写时复用上一阶段的开始时间；切换 stage 时记为 `now`；
    stage 为 `None` 时返回 `None`。
    """
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
    """按"线性外推"估算任务总耗时。

    - `completed` 时返回实际已耗时；
    - `progress` 缺失或为 0 时无法估算，返回 `None`；
    - 其他情况按 `elapsed_seconds / (progress / 100)` 推算。
    """
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
    """根据估算总耗时算剩余时间。

    - 已完成或已取消时返回 `0.0`；
    - 估算总耗时不可用时返回 `None`；
    - 否则返回 `max(0, estimated_total - elapsed)`。
    """
    if status in {"completed", "cancelled"}:
        return 0.0
    if estimated_total_seconds is None:
        return None
    return max(0.0, estimated_total_seconds - elapsed_seconds)
