"""生成层取消上下文与可取消句柄。

集中管理一次生成任务中所有可被取消的子操作（ffmpeg 子进程、
asyncio Task 等）：触发取消后，已经进行中的 LLM 调用、子进程、
待执行的 asyncio Task 都会被一并中断，业务侧通过 `cancel_requested`
或抛 `GenerateCancelledError` 感知。
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Callable, Protocol


class CancellableHandle(Protocol):
    """可注册到 `GenerationCancellationContext` 的取消句柄接口。

    实现必须暴露 `kind` 标识与无副作用的 `cancel()` 方法。
    """

    @property
    def kind(self) -> str: ...
    def cancel(self) -> None: ...


@dataclass
class ProcessHandle:
    """包装一个外部子进程（如 ffmpeg）的取消句柄。

    调用 `cancel()` 会向子进程发送 `kill()` 信号；进程已结束时
    抛出的 `OSError` 会被静默忽略，确保取消路径不会再次抛错。
    """

    kind: str = field(default="process", init=False)
    _proc: object = field(repr=False)

    def cancel(self) -> None:
        """向子进程发送 kill 信号；进程不存在或已结束时忽略 `OSError`。"""
        try:
            self._proc.kill()  # type: ignore[attr-defined]
        except OSError:
            pass


@dataclass
class TaskHandle:
    """包装一个 `asyncio.Task` 的取消句柄。"""

    kind: str = field(default="task", init=False)
    _task: asyncio.Task  # type: ignore[type-arg]

    def cancel(self) -> None:
        """触发 Task 的取消（`asyncio.CancelledError` 会在 await 处抛出）。"""
        self._task.cancel()


class GenerationCancellationContext:
    """单次生成任务的取消上下文。

    业务约束：触发取消后，已经进行中的 LLM 调用会被中断；与生成
    并发的子进程（音频抽取等）会被 kill；注册过的所有句柄都会在
    `request_cancel` 同步路径上被通知一次。线程安全（使用内部锁）。
    """

    def __init__(self, task_id: str) -> None:
        """初始化上下文；`task_id` 仅用于日志与排查。"""
        self.task_id = task_id
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._handles: list[CancellableHandle] = []

    @property
    def cancel_requested(self) -> bool:
        """是否已经处于取消状态（一旦置位不会自动复位）。"""
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        """置位取消事件并同步通知所有已注册句柄。

        通知是「一次性快照」语义：新注册的句柄不会被再次通知，
        但可以通过 `cancel_requested` 自行查询。
        """
        self._cancel_event.set()
        with self._lock:
            handles = list(self._handles)
        for handle in handles:
            handle.cancel()

    def register(self, handle: CancellableHandle) -> None:
        """注册一个可取消句柄；后续 `request_cancel` 会调用其 `cancel()`。"""
        with self._lock:
            self._handles.append(handle)

    def unregister(self, handle: CancellableHandle) -> None:
        """移除已注册句柄；句柄不存在时静默忽略。"""
        with self._lock:
            try:
                self._handles.remove(handle)
            except ValueError:
                pass


async def cancellable_await(
    coro: object,
    ctx: GenerationCancellationContext,
) -> object:
    """Wrap an awaitable so that a cancel request aborts the asyncio Task immediately.

    Args:
        coro: 可等待对象（协程/Future/Task），由调用方负责传递。
        ctx: 关联的取消上下文。

    Returns:
        被包裹的 awaitable 的原始返回值。

    Raises:
        GenerateCancelledError: 上下文已被取消，或被包装的 Task
            收到 `asyncio.CancelledError` 时抛出。
    """
    from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError

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
