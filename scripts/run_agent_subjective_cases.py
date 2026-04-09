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
class SubjectiveAgentCase:
    case_id: str
    title: str
    session_id: str
    message: str
    review_focus: str


SERIES_ID = "agent-frameworks"
VIDEO_ID = "1-4 准备工作：百度地图API秘钥(AK)"
VIDEO_SCOPE_TAG = "overview"


def main() -> int:
    parser = argparse.ArgumentParser(description="运行少量高覆盖的 Agent 主观仿真用例。")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="显式确认本次要运行真实模型对话仿真；默认跳过。",
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
        help="只跑指定 case_id；默认跑全部主观 case。",
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

    if should_skip_manual_only_run(args.manual, "run_agent_subjective_cases.py"):
        return 0

    container = build_container()
    selected_cases = _resolve_cases(args.cases)

    print("=== Agent Subjective Cases ===")
    print(f"workspace: {ROOT}")
    print("说明：本脚本不做 assert，只输出复杂问题下的工具链、事件顺序和最终回答，供人工主观评审。")
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
        report_items.append(
            CaseReportItem(
                case_id=case.case_id,
                title=case.title,
                session_id=case.session_id,
                message=case.message,
                review_focus=case.review_focus,
                status="ok",
                duration_seconds=duration,
                event_order=summarize_event_order(result.raw_events),
                thinking_summaries=result.thinking_summaries,
                tool_rows=result.tool_rows,
                final_answer=result.final_answer or "",
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
        title="Agent 主观用例人工评审报告",
        workspace=ROOT,
        started_at=started_at,
        finished_at=finished_at,
        script="scripts/run_agent_subjective_cases.py",
        args=sys.argv[1:],
    )
    report = render_markdown_report(
        meta,
        report_items,
        include_raw_events=args.show_raw_events,
    )
    print("=== 人工评审报告 (Markdown) ===")
    print(report.rstrip())
    print()
    if args.report_path:
        write_text_report(args.report_path, report)
        print(f"[saved] report_path: {args.report_path}")
        print()

    has_error = any(item.status != "ok" for item in report_items)
    return 1 if has_error else 0


def _resolve_cases(case_ids: list[str] | None) -> list[SubjectiveAgentCase]:
    cases = _build_cases()
    if not case_ids:
        return cases
    requested = {item.strip() for item in case_ids if item.strip()}
    return [case for case in cases if case.case_id in requested]


def _build_cases() -> list[SubjectiveAgentCase]:
    return [
        SubjectiveAgentCase(
            case_id="series-relationship",
            title="系列关系型问题",
            session_id=_series_session("series-relationship"),
            message="百度地图 API Key 这一节和 Nacos 3 这一节在整个课程中分别承担什么作用？它们之间是什么关系？",
            review_focus="期待调用系列侧工具（如 list_series_videos、get_video_summary）来抓取每一节的定位，回答要突出两节的联系，而不是独立列举。",
        ),
        SubjectiveAgentCase(
            case_id="series-concept-location",
            title="系列概念定位",
            session_id=_series_session("series-concept-location"),
            message="这个系列里哪里讲过 Nacos 3？最好指出是哪一节，如果能的话大致说明是在哪个位置或章节。",
            review_focus="要结合 list_series_videos + get_video_summary + 对应 transcript/backreferences 来定位，并给出明确视频/时间节点，避免泛泛而谈。",
        ),
        SubjectiveAgentCase(
            case_id="video-quote-locate",
            title="视频原话定位",
            session_id=_video_session("video-quote-locate"),
            message="视频里哪里提到了 0.0.0.0/0？那一段主要在讲什么？",
            review_focus="同时考查 get_video_transcript 与 video_seek 的配合，既要把原话搬出来，也要解释该段内容，不能只给时间或只给摘要。",
        ),
        SubjectiveAgentCase(
            case_id="video-tool-status",
            title="视频工具状态",
            session_id=_video_session("video-tool-status"),
            message="这个 API Key 视频目前有哪些工具已生成？导图、知识卡片、笔记分别是什么状态？",
            review_focus="观察是否能正确调用 get_video_tools 并列出所有可见资源、状态；重点看工具状态是否明确。",
        ),
        SubjectiveAgentCase(
            case_id="notes-workflow",
            title="笔记工作流",
            session_id=_video_session("notes-workflow"),
            message="请先总结一下这节 API Key 的重点，再把总结保存到笔记里，然后打开笔记让我查阅。",
            review_focus="评估能否处理多步指令，特别是 save_note 和 open_notes 的调用顺序；回答要明确确认保存成功并展示笔记内容。",
        ),
        SubjectiveAgentCase(
            case_id="video-scope-boundary",
            title="video scope 边界",
            session_id=_video_session("video-scope-boundary"),
            message="当前这个视频讲的是 API Key，那后面哪一节最可能与它衔接？",
            review_focus="看是否能在视频范围内保持谦逊推理，结合 summary 判断最自然的接续视频，避免越界胡乱切换。",
        ),
    ]


def _series_session(tag: str) -> str:
    return f"series|{SERIES_ID}|series-home|{tag}"


def _video_session(tag: str) -> str:
    return f"video|{SERIES_ID}|{VIDEO_ID}|{VIDEO_SCOPE_TAG}|{tag}"


if __name__ == "__main__":
    raise SystemExit(main())
