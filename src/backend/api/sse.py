from __future__ import annotations

import asyncio
import json


async def stream_progress_events(*, tracker, task_id: str, terminal_statuses: set[str]):
    last_sequence = -1
    while True:
        snapshot = tracker.get_snapshot(task_id)
        if snapshot.sequence != last_sequence:
            last_sequence = snapshot.sequence
            yield f"data: {json.dumps(snapshot.to_dict(), ensure_ascii=False)}\n\n"
        if snapshot.status in terminal_statuses:
            break
        await asyncio.sleep(0.25)


def encode_sse_event(event_type: str, payload: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
