from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from agent_regression_utils import build_container
from trace_gateway_utils import attach_tracing_gateway


CASE_PRESETS: dict[str, list[str]] = {
    "video-summary-repeat": [
        "这个视频主要讲了什么？",
        "再总结一次这个视频主要讲了什么？",
    ],
    "series-summary-repeat": [
        "这个系列主要讲了哪些主题？",
        "再说一遍这个系列主要讲了哪些主题？",
    ],
    "series-entity-after-summary": [
        "这个系列主要讲了哪些主题？",
        "JManus 是啥？",
    ],
}


SESSION_IDS: dict[str, str] = {
    "video-summary-repeat": "video|agent-frameworks|1-4 准备工作：百度地图API秘钥(AK)|overview|evidence-cache-video",
    "series-summary-repeat": "series|agent-frameworks|series-home|evidence-cache-series",
    "series-entity-after-summary": "series|agent-frameworks|series-home|evidence-cache-entity",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="验证同一会话内是否复用已读证据。")
    parser.add_argument("--case", choices=sorted(CASE_PRESETS), default="series-entity-after-summary")
    args = parser.parse_args()

    session_id = SESSION_IDS[args.case]
    messages = CASE_PRESETS[args.case]
    container = build_container()
    service = container.get_agent_service()
    tracer = attach_tracing_gateway(service)
    service.clear_session(session_id=session_id, context_override=None)

    print("=== evidence-cache-probe ===")
    print(f"case: {args.case}")
    print(f"session_id: {session_id}")
    print()

    for index, message in enumerate(messages, start=1):
        before_records = len(tracer.records)
        result = service.run(session_id=session_id, user_message=message)
        new_records = tracer.records[before_records:]
        print(f"[turn {index}] {message}")
        print("tool_results:")
        print(
            json.dumps(
                [
                    {
                        "tool_name": item.tool_name.value,
                        "status": item.status,
                        "payload_keys": sorted(item.payload.keys()),
                    }
                    for item in result.tool_results
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        print("model_calls:")
        print(
            json.dumps(
                [
                    {
                        "call_kind": item.call_kind,
                        "mode": item.mode,
                        "duration_ms": item.duration_ms,
                        "saw_plan_sentinel": item.saw_plan_sentinel,
                    }
                    for item in new_records
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        print("assistant_message:")
        print(result.assistant_message)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
