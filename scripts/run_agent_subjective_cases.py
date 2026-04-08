from __future__ import annotations

import argparse
from dataclasses import dataclass

from agent_regression_utils import (
    ROOT,
    build_container,
    run_agent_case,
    should_skip_manual_only_run,
    summarize_event_order,
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
    args = parser.parse_args()

    if should_skip_manual_only_run(args.manual, "run_agent_subjective_cases.py"):
        return 0

    container = build_container()
    selected_cases = _resolve_cases(args.cases)

    print("=== Agent Subjective Cases ===")
    print(f"workspace: {ROOT}")
    print("说明：本脚本不做 assert，只输出复杂问题下的工具链、事件顺序和最终回答，供人工主观评审。")
    print()

    for case in selected_cases:
        result = run_agent_case(
            container=container,
            session_id=case.session_id,
            message=case.message,
            clear_session=True,
        )
        _print_case(case, result, show_raw_events=args.show_raw_events)

    _print_review_guide()
    return 0


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
            message="P1 的核心内容和 P2 的核心内容是什么关系？不要分别罗列，要讲它们之间的联系。",
            review_focus="看是否只是分别复述两个视频，还是能真正回答“关系”；同时观察工具是否主要围绕系列 summary 展开。",
        ),
        SubjectiveAgentCase(
            case_id="seek-and-explain",
            title="定位并解释",
            session_id=_video_session("seek-and-explain"),
            message="百度地图 API Key 在视频什么位置提到的？顺便告诉我那一段主要在讲什么。",
            review_focus="看是否同时完成定位与解释；不要只给时间点，也不要只给总结没有定位。",
        ),
        SubjectiveAgentCase(
            case_id="mixed-actions",
            title="多动作复合请求",
            session_id=_video_session("mixed-actions"),
            message="先总结一下这个视频的重点，再帮我记到笔记里，最后把笔记打开。",
            review_focus="看是否能处理混合意图；重点观察工具链是否乱、是否漏掉 save_note/open_notes 之类动作。",
        ),
        SubjectiveAgentCase(
            case_id="cross-video-from-video-scope",
            title="video 上下文问其他视频",
            session_id=_video_session("cross-video-from-video-scope"),
            message="另一个视频里有没有继续讲这个问题？如果有，是哪一个视频？",
            review_focus="看在单 video 上下文下是否会错误越权胡答其他视频，还是能体面说明上下文限制并做合理引导。",
        ),
        SubjectiveAgentCase(
            case_id="series-followup",
            title="系列多轮承接",
            session_id=_series_session("series-followup"),
            message="这个系列主要讲了哪些主题？如果我是新手，应该先看哪一部分？",
            review_focus="看复杂系列问题下是否还能保持自然回答；观察是否出现过度工具调用或明显机械化表达。",
        ),
        SubjectiveAgentCase(
            case_id="out-of-scope-soft-refusal",
            title="超范围自然拒答",
            session_id=_series_session("out-of-scope-soft-refusal"),
            message="帮我写一份旅游攻略，顺便不要调用任何工具。",
            review_focus="看超范围时是否自然拒答，不要暴露内部实现，也不要输出生硬模板。",
        ),
    ]


def _series_session(tag: str) -> str:
    return f"series|{SERIES_ID}|series-home|{tag}"


def _video_session(tag: str) -> str:
    return f"video|{SERIES_ID}|{VIDEO_ID}|{VIDEO_SCOPE_TAG}|{tag}"


def _print_case(case: SubjectiveAgentCase, result, *, show_raw_events: bool) -> None:
    print(f"=== [{case.case_id}] {case.title} ===")
    print(f"session_id: {case.session_id}")
    print(f"message: {case.message}")
    print(f"review_focus: {case.review_focus}")
    print(f"event_order: {summarize_event_order(result.raw_events)}")
    print("思路摘要:")
    if result.thinking_summaries:
        for index, summary in enumerate(result.thinking_summaries, start=1):
            print(f"  [{index}] {summary}")
    else:
        print("  (无)")
    print("工具轨迹:")
    if result.tool_rows:
        for row in result.tool_rows:
            print(f"  {row}")
    else:
        print("  (无)")
    print("最终回答:")
    print(result.final_answer or "(空)")
    if show_raw_events:
        print("原始事件:")
        for item in result.raw_events:
            print(f"  {item}")
    print()


def _print_review_guide() -> None:
    print("=== 建议人工观察点 ===")
    print("- 是否调用了明显不该调用的工具。")
    print("- 是否出现空回答、半截回答、重复回答。")
    print("- 是否泄漏了内部字段，如 tool_name、payload、selected_tool。")
    print("- 复杂问题下是否只是分点复述，而没有真正回答用户问题。")
    print("- video 上下文问其他视频时，是否越界胡答。")
    print("- 超范围问题时，是否自然拒答，而不是输出僵硬模板。")


if __name__ == "__main__":
    raise SystemExit(main())
