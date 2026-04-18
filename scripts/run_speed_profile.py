from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from agent_regression_utils import build_container


CASE_PRESETS: dict[str, tuple[str, str]] = {
    "series-summary": (
        "series|agent-frameworks|series-home|speed-profile-series-summary",
        "这个系列主要讲了哪些主题？",
    ),
    "series-locate": (
        "series|agent-frameworks|series-home|speed-profile-series-locate",
        "这个系列里哪里讲过 Nacos 3？尽量指出视频和大致位置",
    ),
    "video-summary": (
        "video|agent-frameworks|1-4 准备工作：百度地图API秘钥(AK)|overview|speed-profile-video-summary",
        "这个视频主要讲了什么？",
    ),
    "save-note": (
        "video|agent-frameworks|1-4 准备工作：百度地图API秘钥(AK)|notes|speed-profile-save-note",
        "帮我记一下这个视频的重点",
    ),
}


@dataclass
class SpanRecord:
    name: str
    elapsed_ms: int
    meta: dict[str, object] = field(default_factory=dict)


class Profiler:
    def __init__(self) -> None:
        self.records: list[SpanRecord] = []

    @contextmanager
    def span(self, name: str, **meta: object):
        started_at = perf_counter()
        try:
            yield
        finally:
            self.records.append(
                SpanRecord(
                    name=name,
                    elapsed_ms=int((perf_counter() - started_at) * 1000),
                    meta=dict(meta),
                )
            )

    def dump(self) -> dict[str, object]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for record in self.records:
            grouped.setdefault(record.name, []).append(
                {
                    "elapsed_ms": record.elapsed_ms,
                    "meta": record.meta,
                }
            )
        totals = {
            name: sum(item["elapsed_ms"] for item in items)
            for name, items in grouped.items()
        }
        return {
            "records": [
                {
                    "name": record.name,
                    "elapsed_ms": record.elapsed_ms,
                    "meta": record.meta,
                }
                for record in self.records
            ],
            "totals": totals,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="对当前 graph Agent 链路做细粒度速度剖析。")
    parser.add_argument("--case", choices=sorted(CASE_PRESETS), default="series-summary")
    parser.add_argument("--save", action="store_true", help="保存 profile 到 temp/speed-traces/")
    args = parser.parse_args()

    session_id, message = CASE_PRESETS[args.case]
    container = build_container()
    service = container.get_agent_service()
    profiler = Profiler()

    with ExitStack() as stack:
        _attach_service_profiling(stack, service, profiler)
        started_at = perf_counter()
        result = service.run_turn(
            session_id=session_id,
            user_message=message,
        )
        total_elapsed_ms = int((perf_counter() - started_at) * 1000)
        profiler.records.append(SpanRecord(name="graph_service.total", elapsed_ms=total_elapsed_ms, meta={"case": args.case}))

    payload = {
        "case": args.case,
        "session_id": session_id,
        "message": message,
        "assistant_message": result.assistant_message,
        "reason": result.plan.reason,
        "tool_results": [
            {
                "tool_name": item.tool_name.value,
                "status": item.status,
                "payload": item.payload,
            }
            for item in result.tool_results
        ],
        "profile": profiler.dump(),
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.save:
        output_dir = ROOT / "temp" / "speed-traces"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{args.case}.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _attach_service_profiling(stack: ExitStack, service, profiler: Profiler) -> None:
    stack.enter_context(_wrap_method(service, "run_turn", profiler, "graph_service.run_turn"))
    stack.enter_context(_wrap_method(service, "_invoke_graph", profiler, "graph_service._invoke_graph"))

    context_loader = getattr(service, "_context_loader", None)
    if context_loader is not None:
        stack.enter_context(_wrap_method(context_loader, "load", profiler, "context_loader.load"))

    session_store = getattr(service, "_session_store", None)
    if session_store is not None:
        if hasattr(session_store, "get_snapshot"):
            stack.enter_context(_wrap_method(session_store, "get_snapshot", profiler, "session_store.get_snapshot"))
        if hasattr(session_store, "append_turn"):
            stack.enter_context(_wrap_method(session_store, "append_turn", profiler, "session_store.append_turn"))

    graph = getattr(service, "_graph", None)
    if graph is not None and hasattr(graph, "invoke"):
        stack.enter_context(_wrap_method(graph, "invoke", profiler, "graph.invoke"))

    component_specs = [
        ("_decomposer_program", "run", "decomposer.run"),
        ("_classifier_program", "run", "classifier.run"),
        ("_compare_split_program", "run", "compare_split.run"),
        ("_series_planner", "create_plan", "series_planner.create_plan"),
        ("_retrieval_service", "search", "retrieval.search"),
        ("_pinpoint_service", "locate", "pinpoint.locate"),
        ("_meta_state_reader", "read", "meta_state.read"),
        ("_action_dispatcher", "dispatch", "action_dispatcher.dispatch"),
        ("_answer_program", "run", "answer_program.run"),
        ("_memory_update_program", "run", "memory_update.run"),
    ]
    for attr_name, method_name, span_name in component_specs:
        owner = getattr(service, attr_name, None)
        if owner is not None and hasattr(owner, method_name):
            stack.enter_context(_wrap_method(owner, method_name, profiler, span_name))


@contextmanager
def _wrap_method(owner, method_name: str, profiler: Profiler, span_name: str):
    original = getattr(owner, method_name)

    def _wrapped(*args, **kwargs):
        with profiler.span(span_name):
            return original(*args, **kwargs)

    setattr(owner, method_name, _wrapped)
    try:
        yield
    finally:
        setattr(owner, method_name, original)


if __name__ == "__main__":
    raise SystemExit(main())
