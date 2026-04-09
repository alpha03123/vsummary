from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import sys
import time

from agent_regression_utils import (
    ROOT,
    build_container,
    run_agent_case,
    should_skip_manual_only_run,
    summarize_event_order,
)
from review_report_utils import (
    CaseReportItem,
    ReportMeta,
    render_markdown_report,
    write_text_report,
)


@dataclass(frozen=True)
class ActionCase:
    case_id: str
    title: str
    session_id: str
    message: str
    review_focus: str


SERIES_ID = "agent-frameworks"
VIDEO_ID = "1-4 准备工作：百度地图API秘钥(AK)"


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Agent 动作矩阵主观回归。")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="显式确认本次要运行真实模型动作矩阵；默认跳过。",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="某个 case 运行失败时继续跑后续 case；最后根据汇总结果返回非 0。",
    )
    parser.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="只跑指定 case_id；默认跑全部动作 case。",
    )
    parser.add_argument(
        "--show-raw-events",
        action="store_true",
        help="打印每个 case 的完整原始事件。",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="将最终人工评审报告另存为 Markdown 文件（默认只打印到 stdout）。",
    )
    args = parser.parse_args()

    if should_skip_manual_only_run(args.manual, "run_agent_action_matrix.py"):
        return 0

    container = build_container()
    selected_cases = _resolve_cases(args.cases)

    print("=== Agent Action Matrix ===")
    print(f"workspace: {ROOT}")
    print("说明：本脚本用于人工观察动作类请求是否走到正确工具链，不做 assert。")
    print()

    started_at = datetime.now().astimezone()
    report_items: list[CaseReportItem] = []

    for case in selected_cases:
        print(f"--- running: [{case.case_id}] {case.title} ---")
        started_case = time.perf_counter()
        try:
            result = run_agent_case(
                container=container,
                session_id=case.session_id,
                message=case.message,
                clear_session=True,
            )
        except Exception as exc:
            duration = time.perf_counter() - started_case
            report_items.append(
                CaseReportItem.from_exception(
                    case_id=case.case_id,
                    title=case.title,
                    session_id=case.session_id,
                    message=case.message,
                    review_focus=case.review_focus,
                    duration_seconds=duration,
                    exc=exc,
                )
            )
            print(f"[error] {case.case_id}: {type(exc).__name__}: {exc}")
            print()
            if not args.continue_on_error:
                break
            continue

        duration = time.perf_counter() - started_case
        event_order = summarize_event_order(result.raw_events)
        thinking_summaries = result.thinking_summaries
        tool_rows = result.tool_rows
        final_answer = result.final_answer or ""
        _print_case_outcome(
            review_focus=case.review_focus,
            event_order=event_order,
            thinking_summaries=thinking_summaries,
            tool_rows=tool_rows,
            final_answer=final_answer,
        )
        report_items.append(
            CaseReportItem(
                case_id=case.case_id,
                title=case.title,
                session_id=case.session_id,
                message=case.message,
                review_focus=case.review_focus,
                status="ok",
                duration_seconds=duration,
                event_order=event_order,
                thinking_summaries=thinking_summaries,
                tool_rows=tool_rows,
                final_answer=final_answer,
                raw_events=result.raw_events if args.show_raw_events else None,
                error_type=None,
                error_message=None,
                error_traceback=None,
            )
        )
        print(
            f"[ok] {case.case_id}: duration_s={duration:.3f}, tools={len(result.tool_rows)}, "
            f"thinking={len(result.thinking_summaries)}, answer_len={len(result.final_answer or '')}"
        )
        print()

    finished_at = datetime.now().astimezone()
    meta = ReportMeta(
        title="Agent 动作矩阵人工评审报告",
        workspace=ROOT,
        started_at=started_at,
        finished_at=finished_at,
        script="scripts/run_agent_action_matrix.py",
        args=sys.argv[1:],
    )
    report = render_markdown_report(meta, report_items, include_raw_events=args.show_raw_events)
    print("=== 人工评审报告 (Markdown) ===")
    print(report.rstrip())
    print()

    if args.report_path:
        write_text_report(args.report_path, report)
        print(f"[saved] report_path: {args.report_path}")
        print()

    has_error = any(item.status != "ok" for item in report_items)
    return 1 if has_error else 0


def _resolve_cases(case_ids: list[str] | None) -> list[ActionCase]:
    cases = _build_cases()
    if not case_ids:
        return cases
    requested = {item.strip() for item in case_ids if item.strip()}
    return [case for case in cases if case.case_id in requested]


def _build_cases() -> list[ActionCase]:
    return [
        ActionCase(
            case_id="open-series-home",
            title="打开系列首页",
            session_id=f"series|{SERIES_ID}|series-home|open-series-home",
            message="打开系列首页",
            review_focus="覆盖 open_series_home，观察是否直接执行动作，不绕到问答。",
        ),
        ActionCase(
            case_id="open-series-overview",
            title="打开系列概览",
            session_id=f"series|{SERIES_ID}|series-home|open-series-overview",
            message="打开系列概览",
            review_focus="覆盖 open_series_overview，观察是否直接切换系列概览。",
        ),
        ActionCase(
            case_id="open-overview",
            title="打开概况",
            session_id=f"video|{SERIES_ID}|{VIDEO_ID}|overview|open-overview",
            message="打开概况",
            review_focus="覆盖 open_overview；若概况缺失，可能联动 generate_overview。",
        ),
        ActionCase(
            case_id="open-mindmap",
            title="打开思维导图",
            session_id=f"video|{SERIES_ID}|{VIDEO_ID}|mindmap|open-mindmap",
            message="打开思维导图",
            review_focus="覆盖 open_mindmap；若导图缺失，可能联动 generate_mindmap。",
        ),
        ActionCase(
            case_id="open-knowledge-cards",
            title="打开知识卡片",
            session_id=f"video|{SERIES_ID}|{VIDEO_ID}|overview|open-knowledge-cards",
            message="打开知识卡片",
            review_focus="覆盖 open_knowledge_cards。",
        ),
        ActionCase(
            case_id="open-video",
            title="打开视频",
            session_id=f"video|{SERIES_ID}|{VIDEO_ID}|overview|open-video",
            message="打开视频",
            review_focus="覆盖 open_video。",
        ),
        ActionCase(
            case_id="generate-overview",
            title="生成概况",
            session_id=f"video|{SERIES_ID}|{VIDEO_ID}|overview|generate-overview",
            message="生成概况",
            review_focus="覆盖 generate_overview。",
        ),
        ActionCase(
            case_id="generate-mindmap",
            title="生成导图",
            session_id=f"video|{SERIES_ID}|{VIDEO_ID}|mindmap|generate-mindmap",
            message="生成导图",
            review_focus="覆盖 generate_mindmap。",
        ),
    ]


def _print_case_outcome(
    *,
    review_focus: str,
    event_order: list[str],
    thinking_summaries: list[str],
    tool_rows: list[str],
    final_answer: str,
) -> None:
    print("#### 当前用例输出概览")
    print(f"- review_focus: {review_focus}")
    print(f"- event_order: {event_order}")
    print("- thinking_summaries:")
    if thinking_summaries:
        for index, summary in enumerate(thinking_summaries, start=1):
            print(f"  - [{index}] {summary}")
    else:
        print("  - (无)")
    print("- tool_rows:")
    if tool_rows:
        for row in tool_rows:
            print(f"  {row}")
    else:
        print("  - (无)")
    print("- final_answer:")
    print("```")
    print(final_answer or "(空)")
    print("```")
    print()


if __name__ == "__main__":
    raise SystemExit(main())
