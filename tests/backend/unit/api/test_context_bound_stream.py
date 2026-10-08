import asyncio
from contextvars import Context

import pytest
from starlette.concurrency import iterate_in_threadpool

from backend.api.schemas.sse import context_bound_iterator
from backend.core.metering import bind_resource_budget, current_operation_id


@pytest.mark.parametrize("close_early", [False, True])
def test_stream_keeps_token_context_across_next_and_close(close_early):
    finalized = []
    def events():
        with bind_resource_budget(None, "operation-1"):
            try:
                yield current_operation_id()
                yield current_operation_id()
            finally:
                finalized.append(current_operation_id())
    iterator = context_bound_iterator(events())
    assert Context().run(next, iterator) == "operation-1"
    assert current_operation_id() is None
    if close_early:
        Context().run(iterator.close)
    else:
        assert Context().run(next, iterator) == "operation-1"
        with pytest.raises(StopIteration):
            Context().run(next, iterator)
    assert finalized == ["operation-1"]
    assert current_operation_id() is None


def test_starlette_threadpool_streams_do_not_share_usage_operation():
    def events(operation_id):
        with bind_resource_budget(None, operation_id):
            yield current_operation_id()
            yield current_operation_id()
    async def consume(operation_id):
        return [item async for item in iterate_in_threadpool(context_bound_iterator(events(operation_id)))]
    async def run():
        return await asyncio.gather(consume("first"), consume("second"))
    assert asyncio.run(run()) == [["first", "first"], ["second", "second"]]
