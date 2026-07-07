"""SSE（Server-Sent Events）流式推送工具。

提供进度事件流的异步生成器与 SSE 帧编码函数，供 FastAPI 路由
通过 ``StreamingResponse`` 向客户端推送实时进度更新。
"""

from __future__ import annotations

import asyncio
import json


async def stream_progress_events(*, tracker, task_id: str, terminal_statuses: set[str]):
    """以 SSE 流的形式推送任务的进度快照。

    每隔 0.25 秒轮询一次 ``tracker``，仅当快照序号变化时才推送新事件，
    避免重复发送相同进度。当快照状态落入 ``terminal_statuses`` 时，
    流自动结束，客户端据此判定任务已完成/失败。

    Args:
        tracker: 进度追踪器实例（需有 ``get_snapshot(task_id)`` 方法）。
        task_id: 待追踪的任务 ID。
        terminal_statuses: 终止状态集合，命中后停止推送。

    Yields:
        SSE 格式的字符串帧，每帧为一个 ``data:`` 行加空行。
    """
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
    """将一个事件类型和 JSON 负载编码为 SSE 帧。

    帧格式为：
        event: <event_type>
        data: <JSON>
        <空行>

    该格式兼容浏览器的 ``EventSource`` API，前端可按 ``event_type``
    注册不同的 ``addEventListener`` 处理逻辑。

    Args:
        event_type: SSE 事件类型字符串（如 "progress"、"error"、"done"）。
        payload: 待序列化为 JSON 的事件负载。

    Returns:
        完整的 SSE 帧字符串，可直接写入 ``StreamingResponse`` 的 body。
    """
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
