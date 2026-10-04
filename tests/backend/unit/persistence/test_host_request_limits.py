from multiprocessing import get_context
from pathlib import Path
import asyncio
import time

import pytest

from backend.core.concurrency import FileRequestLimiter, bind_request_limiter, request_slot, async_request_slot, limited_completion


def _hold_slot(root, entered):
    limiter = FileRequestLimiter(Path(root), {"llm": 1})
    with bind_request_limiter(limiter), request_slot("llm"):
        entered.set()
        time.sleep(30)


def test_budget_is_shared_across_processes_and_released_on_exit(tmp_path):
    context = get_context("spawn")
    entered = context.Event()
    process = context.Process(target=_hold_slot, args=(str(tmp_path), entered))
    process.start()
    try:
        assert entered.wait(10)
        limiter = FileRequestLimiter(tmp_path, {"llm": 1})
        assert limiter.try_acquire("llm") is None
        process.terminate()
        process.join(10)
        lock = limiter.try_acquire("llm")
        assert lock is not None
        lock.release()
    finally:
        if process.is_alive():
            process.terminate()
        process.join(10)


def test_stream_holds_its_slot_until_closed(tmp_path):
    limiter = FileRequestLimiter(tmp_path, {"llm": 1})
    with bind_request_limiter(limiter):
        stream = limited_completion(lambda **_: iter(["a", "b"]))(stream=True)
        assert next(stream) == "a"
        assert limiter.try_acquire("llm") is None
        stream.close()
        lock = limiter.try_acquire("llm")
        assert lock is not None
        lock.release()


def test_different_process_budget_configuration_is_rejected(tmp_path):
    FileRequestLimiter(tmp_path, {"llm": 1})
    with pytest.raises(ValueError, match="budgets differ"):
        FileRequestLimiter(tmp_path, {"llm": 2})


def test_async_cancellation_while_waiting_does_not_leak_a_slot(tmp_path):
    async def scenario():
        limiter = FileRequestLimiter(tmp_path, {"llm": 1})
        with bind_request_limiter(limiter):
            async with async_request_slot("llm"):
                async def wait():
                    async with async_request_slot("llm"):
                        pytest.fail("waiter should not acquire")
                task = asyncio.create_task(wait())
                await asyncio.sleep(0.05)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            lock = limiter.try_acquire("llm")
            assert lock is not None
            lock.release()
    asyncio.run(scenario())
