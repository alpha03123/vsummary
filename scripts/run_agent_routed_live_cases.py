from __future__ import annotations

import argparse
from dataclasses import dataclass

from agent_regression_utils import (
    ROOT,
    build_container,
    run_agent_case,
    summarize_event_order,
)


@dataclass(frozen=True)
class RoutedLiveCase:
    case_id: str
    title: str
    session_id: str
    message: str
    note: str


SERIES_ID = "agent-frameworks"
VIDEO_ID = "1-4 准备工作：百度地图API秘钥(AK)"


def main() -> int:
    parser = argparse.ArgumentParser(description="运行新主路径的真实 Agent 仿真回归。")
    parser.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="只跑指定 case_id；默认跑全部 routed live case。",
    )
    parser.add_argument(
        "--show-raw-events",
        action="store_true",
        help="打印每个 case 的完整原始事件。",
    )
    args = parser.parse_args()

    container = build_container()
    selected_cases = _resolve_cases(args.cases)

    print("=== Routed Live Cases ===")
    print(f"workspace: {ROOT}")
    print()

    for case in selected_cases:
        result = run_agent_case(
            container=container,
            session_id=case.session_id,
            message=case.message,
            clear_session=True,
        )
        _print_case(case, result, show_raw_events=args.show_raw_events)

    return 0


def _resolve_cases(case_ids: list[str] | None) -> list[RoutedLiveCase]:
    cases = _build_cases()
    if not case_ids:
        return cases
    requested = {item.strip() for item in case_ids if item.strip()}
    return [case for case in cases if case.case_id in requested]


def _build_cases() -> list[RoutedLiveCase]:
    return [
        RoutedLiveCase(
            case_id="series-summary",
            title="系列主题概括",
            session_id=_series_session("series-summary"),
            message="这个系列主要讲了哪些主题？要阅读大纲",
            note="预期优先走新的 series_summary 主路径，再批量读取 summary。",
        ),
        RoutedLiveCase(
            case_id="series-locate",
            title="系列概念定位",
            session_id=_series_session("series-locate"),
            message="这个系列里哪里讲过 Nacos 3？尽量指出视频和大致位置",
            note="预期先批量读 summary，再筛候选视频，再读 transcript 做系列级定位。",
        ),
        RoutedLiveCase(
            case_id="video-summary",
            title="视频概括",
            session_id=_video_session("video-summary"),
            message="这个视频主要讲了什么？",
            note="预期优先走 video_summary 主路径，先读 summary 再回答。",
        ),
        RoutedLiveCase(
            case_id="video-transcript",
            title="视频原话",
            session_id=_video_session("video-transcript"),
            message="视频原话里是怎么说的？尽量按原话回答",
            note="预期优先走 video_transcript 主路径，先读 transcript 再回答。",
        ),
        RoutedLiveCase(
            case_id="save-note",
            title="记录重点",
            session_id=_video_session("save-note"),
            message="帮我记一下这个视频的重点",
            note="预期走 save_note 主路径，先读证据，再直接整理并保存笔记。",
        ),
        RoutedLiveCase(
            case_id="open-overview",
            title="打开概况",
            session_id=_video_session("open-overview"),
            message="打开概况",
            note="预期走 open_tool 主路径，直接执行动作并返回确定性回复。",
        ),
        RoutedLiveCase(
            case_id="open-cards",
            title="打开知识卡片",
            session_id=_video_session("open-cards"),
            message="打开知识卡片",
            note="预期走 open_tool 主路径，直接执行知识卡片切换。",
        ),
        RoutedLiveCase(
            case_id="open-notes",
            title="打开笔记",
            session_id=_video_session("open-notes"),
            message="打开笔记",
            note="预期走 open_tool 主路径，直接执行笔记页切换。",
        ),
        RoutedLiveCase(
            case_id="open-video",
            title="打开视频",
            session_id=_video_session("open-video"),
            message="打开视频",
            note="预期走 open_tool 主路径，直接执行视频页切换。",
        ),
        RoutedLiveCase(
            case_id="open-series-overview",
            title="打开系列概览",
            session_id=_series_session("open-series-overview"),
            message="打开系列概览",
            note="预期走 open_tool 主路径，直接执行系列页面切换。",
        ),
        RoutedLiveCase(
            case_id="generate-overview",
            title="生成概况",
            session_id=_video_session("generate-overview"),
            message="生成概况",
            note="预期走 generate_overview 主路径，执行生成并直接返回确定性回复。",
        ),
        RoutedLiveCase(
            case_id="generate-mindmap",
            title="生成导图",
            session_id=_video_session("generate-mindmap"),
            message="生成导图",
            note="预期走 generate_mindmap 主路径，执行生成并直接返回确定性回复。",
        ),
        RoutedLiveCase(
            case_id="out-of-scope",
            title="超范围请求",
            session_id=_series_session("out-of-scope"),
            message="帮我写一份旅游攻略",
            note="预期走 out_of_scope 主路径，直接返回确定性拒答，不进入 planner。",
        ),
    ]


def _series_session(tag: str) -> str:
    return f"series|{SERIES_ID}|series-home|{tag}"


def _video_session(tag: str) -> str:
    return f"video|{SERIES_ID}|{VIDEO_ID}|overview|{tag}"


def _print_case(case: RoutedLiveCase, result, *, show_raw_events: bool) -> None:
    print(f"=== [{case.case_id}] {case.title} ===")
    print(f"session_id: {case.session_id}")
    print(f"message: {case.message}")
    print(f"note: {case.note}")
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


if __name__ == "__main__":
    raise SystemExit(main())
