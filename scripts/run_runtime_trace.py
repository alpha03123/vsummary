from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from agent_regression_utils import build_container
from trace_gateway_utils import attach_tracing_gateway, format_trace_summary


CASE_PRESETS: dict[str, tuple[str, str]] = {
    "series-summary": ("series|agent-frameworks|series-home|runtime-trace-series-summary", "这个系列主要讲了哪些主题？"),
    "series-locate": ("series|agent-frameworks|series-home|runtime-trace-series-locate", "这个系列里哪里讲过 Nacos 3？尽量指出视频和大致位置"),
    "video-summary": ("video|agent-frameworks|1-4 准备工作：百度地图API秘钥(AK)|overview|runtime-trace-video-summary", "这个视频主要讲了什么？"),
    "save-note": ("video|agent-frameworks|1-4 准备工作：百度地图API秘钥(AK)|notes|runtime-trace-save-note", "帮我记一下这个视频的重点"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="输出 runtime 级事件与模型调用时序。")
    parser.add_argument("--case", choices=sorted(CASE_PRESETS), default="series-summary")
    parser.add_argument("--show-deltas", action="store_true", help="是否打印 thinking_delta / answer_delta 细粒度事件。")
    args = parser.parse_args()

    session_id, message = CASE_PRESETS[args.case]
    container = build_container()
    service = container.get_agent_service()
    tracer = attach_tracing_gateway(service)
    service.clear_session(session_id=session_id, context_override=None)

    started_at = perf_counter()
    first_tool_started_ms: int | None = None
    events: list[dict[str, object]] = []

    for event in service.stream_with_context(
        session_id=session_id,
        user_message=message,
        context_override=None,
    ):
        relative_ms = max(0, int((perf_counter() - started_at) * 1000))
        if args.show_deltas or event.type not in {"thinking_delta", "answer_delta"}:
            events.append(
                {
                    "type": event.type,
                    "payload": event.payload,
                    "t_ms": relative_ms,
                }
            )
        if event.type == "tool_started" and first_tool_started_ms is None:
            first_tool_started_ms = relative_ms

    print("=== runtime-trace ===")
    print(f"case: {args.case}")
    print(f"message: {message}")
    print(f"first_tool_started_ms: {first_tool_started_ms}")
    print(f"total_duration_ms: {max(0, int((perf_counter() - started_at) * 1000))}")
    print(format_trace_summary(tracer.records))
    print("events:")
    print(json.dumps(events, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
