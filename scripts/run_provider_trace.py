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


CASE_PRESETS: dict[str, tuple[str, str]] = {
    "series-summary": ("series|agent-frameworks|series-home|provider-trace-series-summary", "这个系列主要讲了哪些主题？"),
    "series-locate": ("series|agent-frameworks|series-home|provider-trace-series-locate", "这个系列里哪里讲过 Nacos 3？尽量指出视频和大致位置"),
    "open-mindmap": ("video|agent-frameworks|1-5 准备工作：安装Nacos 3|mindmap|provider-trace-open-mindmap", "打开思维导图"),
    "save-note": ("video|agent-frameworks|1-4 准备工作：百度地图API秘钥(AK)|notes|provider-trace-save-note", "帮我记一下这个视频的重点"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="输出一轮请求实际触发的模型调用分布。")
    parser.add_argument("--case", choices=sorted(CASE_PRESETS), default="series-summary")
    args = parser.parse_args()

    session_id, message = CASE_PRESETS[args.case]
    container = build_container()
    service = container.get_agent_service()
    tracer = attach_tracing_gateway(service)
    service.clear_session(session_id=session_id, context_override=None)
    service.run(session_id=session_id, user_message=message)

    summary = {
        "case": args.case,
        "message": message,
        "total_model_calls": len(tracer.records),
        "by_kind": _count_by_kind(tracer.records),
        "calls": [
            {
                "call_kind": item.call_kind,
                "mode": item.mode,
                "duration_ms": item.duration_ms,
                "saw_plan_sentinel": item.saw_plan_sentinel,
            }
            for item in tracer.records
        ],
    }
    print("=== provider-trace ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _count_by_kind(records) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in records:
        counts[item.call_kind] = counts.get(item.call_kind, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
