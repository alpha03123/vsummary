"""Same-host request budgets shared by API and worker processes."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Protocol

from filelock import FileLock, Timeout


class RequestLimitTimeout(TimeoutError):
    """The host could not admit a request before its acquisition deadline."""


class RequestLimiter(Protocol):
    def try_acquire(self, resource: str) -> FileLock | None: ...

    acquisition_timeout: float
    poll_seconds: float


class FileRequestLimiter:
    """OS file locks bound concurrent work on one server, including crashes.

    Every process must use the same root and budget file. Budget changes require
    stopping all processes and removing budgets.json before restarting them.
    """

    def __init__(
        self,
        root: Path,
        limits: dict[str, int],
        *,
        acquisition_timeout: float = 60,
        poll_seconds: float = 0.05,
    ):
        if not limits or any(
            not name.isidentifier() or count < 1 for name, count in limits.items()
        ):
            raise ValueError(
                "Request budgets require resource names and positive limits."
            )
        if acquisition_timeout <= 0 or poll_seconds <= 0:
            raise ValueError("Request limiter timeouts must be positive.")
        self.root = root
        self.limits = dict(limits)
        self.acquisition_timeout = acquisition_timeout
        self.poll_seconds = poll_seconds
        root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(root / "budgets.lock")):
            manifest = root / "budgets.json"
            if manifest.exists():
                if json.loads(manifest.read_text(encoding="utf-8")) != self.limits:
                    raise ValueError(
                        "Server request budgets differ from the existing deployment."
                    )
            else:
                manifest.write_text(
                    json.dumps(self.limits, sort_keys=True), encoding="utf-8"
                )

    def try_acquire(self, resource: str) -> FileLock | None:
        count = self.limits[resource]
        for index in range(count):
            lock = FileLock(
                str(self.root / f"{resource}-{index}.lock"), thread_local=False
            )
            try:
                lock.acquire(timeout=0)
                return lock
            except Timeout:
                continue
        return None


_limiter: ContextVar[RequestLimiter | None] = ContextVar(
    "request_limiter", default=None
)


@contextmanager
def bind_request_limiter(limiter: RequestLimiter | None):
    token = _limiter.set(limiter)
    try:
        yield
    finally:
        _limiter.reset(token)


@contextmanager
def request_slot(resource: str):
    limiter = _limiter.get()
    if limiter is None:
        yield
        return
    deadline = time.monotonic() + limiter.acquisition_timeout
    while (lock := limiter.try_acquire(resource)) is None:
        if time.monotonic() >= deadline:
            raise RequestLimitTimeout(f"Request budget exhausted: {resource}")
        time.sleep(limiter.poll_seconds)
    try:
        yield
    finally:
        lock.release()


@asynccontextmanager
async def async_request_slot(resource: str):
    limiter = _limiter.get()
    if limiter is None:
        yield
        return
    deadline = time.monotonic() + limiter.acquisition_timeout
    while (lock := limiter.try_acquire(resource)) is None:
        if time.monotonic() >= deadline:
            raise RequestLimitTimeout(f"Request budget exhausted: {resource}")
        await asyncio.sleep(limiter.poll_seconds)
    try:
        yield
    finally:
        lock.release()


def limited_completion(call):
    def invoke(**kwargs):
        if kwargs.get("stream"):
            return stream(**kwargs)
        with request_slot("llm"):
            return call(**kwargs)

    def stream(**kwargs):
        with request_slot("llm"):
            result = call(**kwargs)
            try:
                yield from result
            finally:
                if hasattr(result, "close"):
                    result.close()

    return invoke


def limited_async_completion(call):
    async def invoke(**kwargs):
        if kwargs.get("stream"):
            return stream(**kwargs)
        async with async_request_slot("llm"):
            return await call(**kwargs)

    async def stream(**kwargs):
        async with async_request_slot("llm"):
            result = await call(**kwargs)
            try:
                async for item in result:
                    yield item
            finally:
                if hasattr(result, "aclose"):
                    await result.aclose()

    return invoke
