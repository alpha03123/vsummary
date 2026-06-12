from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Callable, Protocol


class CancellableHandle(Protocol):
    @property
    def kind(self) -> str: ...
    def cancel(self) -> None: ...


@dataclass
class ProcessHandle:
    kind: str = field(default="process", init=False)
    _proc: object = field(repr=False)

    def cancel(self) -> None:
        try:
            self._proc.kill()  # type: ignore[attr-defined]
        except OSError:
            pass


@dataclass
class TaskHandle:
    kind: str = field(default="task", init=False)
    _task: asyncio.Task  # type: ignore[type-arg]

    def cancel(self) -> None:
        self._task.cancel()


class GenerationCancellationContext:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._handles: list[CancellableHandle] = []

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            handles = list(self._handles)
        for handle in handles:
            handle.cancel()

    def register(self, handle: CancellableHandle) -> None:
        with self._lock:
            self._handles.append(handle)

    def unregister(self, handle: CancellableHandle) -> None:
        with self._lock:
            try:
                self._handles.remove(handle)
            except ValueError:
                pass


async def cancellable_await(
    coro: object,
    ctx: GenerationCancellationContext,
) -> object:
    """Wrap an awaitable so that a cancel request aborts the asyncio Task immediately."""
    from backend.video_summary.summary_generation.usecases.generate_summary import GenerateCancelledError

    if ctx.cancel_requested:
        raise GenerateCancelledError("任务已取消")

    task: asyncio.Task = asyncio.ensure_future(coro)  # type: ignore[arg-type]
    handle = TaskHandle(_task=task)
    ctx.register(handle)
    try:
        return await task
    except asyncio.CancelledError:
        raise GenerateCancelledError("任务已取消")
    finally:
        ctx.unregister(handle)
