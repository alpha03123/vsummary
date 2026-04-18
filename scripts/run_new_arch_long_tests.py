from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from agent_regression_utils import (
    ROOT,
    build_container,
    run_agent_case,
    should_skip_manual_only_run,
    summarize_event_order,
)


@dataclass(frozen=True)
class LongTestTurn:
    message: str


@dataclass(frozen=True)
class LongTestCase:
    case_id: str
    title: str
    session_id: str
    turns: tuple[LongTestTurn, ...]
    focus: str


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 graph 架构第一批真实长测试。")
    parser.add_argument("--manual", action="store_true", help="显式确认要运行真实模型长测试；默认跳过。")
    parser.add_argument("--cases", nargs="*", default=None, help="只运行指定 case_id。")
    parser.add_argument("--show-raw-events", action="store_true", help="打印完整原始事件。")
    parser.add_argument("--max-turns", type=int, default=None, help="每个 case 最多执行多少轮；默认执行全部轮次。")
    parser.add_argument("--save-trace", action="store_true", help="将每个 case 的执行结果落盘到 temp/long-test-traces/。")
    parser.add_argument("--debug-trace", action="store_true", help="在 trace 中附带 graph 中间调试数据。")
    args = parser.parse_args()

    if should_skip_manual_only_run(args.manual, "run_new_arch_long_tests.py"):
        return 0

    cases = _resolve_cases(args.cases)
    container = build_container()

    print("=== graph 架构真实长测试 ===")
    print(f"workspace: {ROOT}")
    print()

    for case in cases:
        _run_case(
            container=container,
            case=case,
            show_raw_events=args.show_raw_events,
            max_turns=args.max_turns,
            save_trace=args.save_trace,
            debug_trace=args.debug_trace,
        )
    return 0


def _resolve_cases(case_ids: list[str] | None) -> list[LongTestCase]:
    cases = _build_cases()
    if not case_ids:
        return cases
    requested = {item.strip() for item in case_ids if item.strip()}
    return [case for case in cases if case.case_id in requested]


def _build_cases() -> list[LongTestCase]:
    return [
        LongTestCase(
            case_id="lt-01-setup-filter",
            title="环境准备课筛选",
            session_id="series|agent-frameworks|series-home|lt-01",
            turns=(
                LongTestTurn(
                    message="把 agent-frameworks 这个系列里，真正属于“安装 / 初始化 / 环境准备”的视频找出来，并按先后顺序告诉我每节到底在准备什么。不要把纯概念介绍的视频算进去。"
                ),
            ),
            focus="series summary 筛选与排除能力。",
        ),
        LongTestCase(
            case_id="lt-02-nacos-locate",
            title="Nacos 安装与控制台信息定位",
            session_id="series|agent-frameworks|series-home|lt-02",
            turns=(
                LongTestTurn(
                    message="在 agent-frameworks 里，老师具体是在哪一节用 Docker 安装 Nacos 3 的？大概从哪一分开始讲安装命令，后面又在哪一段讲了端口和默认登录信息？"
                ),
            ),
            focus="series 到 video 的收缩，以及 transcript 深定位。",
        ),
        LongTestCase(
            case_id="lt-03-framework-followup",
            title="先筛框架课，再跨轮对比",
            session_id="series|agent-frameworks|series-home|lt-03",
            turns=(
                LongTestTurn(
                    message="agent-frameworks 里，哪几节是在讲多智能体框架本身，而不是讲环境安装？"
                ),
                LongTestTurn(
                    message="好，那就在你刚才找出的这几节里，帮我对比一下 JManus 和 AgentScope 的定位差异、依赖生态差异，以及它们对 ReAct 的关系。"
                ),
            ),
            focus="跨轮上下文继承与跨视频比较。",
        ),
        LongTestCase(
            case_id="lt-04-jmanus-flow",
            title="JManus 示例执行链",
            session_id="series|agent-frameworks|series-home|lt-04",
            turns=(
                LongTestTurn(
                    message="JManus 那节里，老师演示的完整任务到底是什么？系统创建了哪几个 Agent，各自负责什么，最后文件被保存到了哪里？请尽量按视频里的执行顺序说。"
                ),
            ),
            focus="单视频深理解与流程化回答。",
        ),
        LongTestCase(
            case_id="lt-05-mixed-depth",
            title="系列脉络加单点深挖",
            session_id="series|agent-frameworks|series-home|lt-05",
            turns=(
                LongTestTurn(
                    message="从高层看，agent-frameworks 这个系列前几节是怎么一步步从环境准备过渡到多智能体框架介绍的？先给我一个整体脉络。然后单独把 AgentScope 那节里老师怎么解释 ReAct 的，按原意展开讲清楚。"
                ),
            ),
            focus="混合深度子计划与答案编排。",
        ),
    ]


def _run_case(
    *,
    container,
    case: LongTestCase,
    show_raw_events: bool,
    max_turns: int | None,
    save_trace: bool,
    debug_trace: bool,
) -> None:
    print(f"=== [{case.case_id}] {case.title} ===")
    print(f"focus: {case.focus}")
    print(f"session_id: {case.session_id}")
    print()

    turns = case.turns if max_turns is None else case.turns[: max(0, max_turns)]
    trace_rows: list[dict[str, object]] = []
    for index, turn in enumerate(turns, start=1):
        result = run_agent_case(
            container=container,
            session_id=case.session_id,
            message=turn.message,
            clear_session=index == 1,
            debug_trace=debug_trace,
        )
        print(f"--- turn {index} ---")
        print(f"message: {turn.message}")
        print(f"event_order: {summarize_event_order(result.raw_events)}")
        print("thinking:")
        if result.thinking_summaries:
            for item in result.thinking_summaries:
                print(f"  - {item}")
        else:
            print("  - (无)")
        print("tools:")
        if result.tool_rows:
            for row in result.tool_rows:
                print(f"  {row}")
        else:
            print("  (无)")
        print("answer:")
        print(result.final_answer or "(空)")
        if show_raw_events:
            print("raw_events:")
            for item in result.raw_events:
                print(f"  {item}")
        if debug_trace:
            print("debug_trace:")
            print(json.dumps(result.debug_trace, ensure_ascii=False, indent=2))
        print()
        trace_rows.append(
            {
                "turn_index": index,
                "message": turn.message,
                "event_order": summarize_event_order(result.raw_events),
                "thinking_summaries": result.thinking_summaries,
                "tool_rows": result.tool_rows,
                "final_answer": result.final_answer,
                "duration_ms": result.raw_events[-1]["elapsed_ms"] if result.raw_events else 0,
                "raw_events": result.raw_events,
                "debug_trace": result.debug_trace if debug_trace else {},
            }
        )
    if save_trace:
        _save_case_trace(case=case, trace_rows=trace_rows)


def _save_case_trace(*, case: LongTestCase, trace_rows: list[dict[str, object]]) -> None:
    output_dir = ROOT / "temp" / "long-test-traces"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{case.case_id}.json"
    payload = {
        "case_id": case.case_id,
        "title": case.title,
        "session_id": case.session_id,
        "focus": case.focus,
        "turns": trace_rows,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
