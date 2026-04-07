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
class ManualAgentCase:
    case_id: str
    title: str
    session_id: str
    message: str
    note: str = ""


SERIES_ID = "agent-frameworks"
VIDEO_ID = "1-4 准备工作：百度地图API秘钥(AK)"


def main() -> int:
    parser = argparse.ArgumentParser(description="手动运行低优先级的 Agent 对话手测回归。")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="显式确认本次要运行真实模型对话回归；默认跳过。",
    )
    parser.add_argument(
        "--cases",
        nargs="*",
        default=None,
        help="只跑指定 case_id；默认跑核心场景与预算/恢复检查。",
    )
    parser.add_argument(
        "--show-raw-events",
        action="store_true",
        help="打印每个 case 的完整原始事件。",
    )
    parser.add_argument(
        "--skip-budget",
        action="store_true",
        help="跳过上下文预算专项。",
    )
    parser.add_argument(
        "--skip-recovery",
        action="store_true",
        help="跳过会话恢复专项。",
    )
    args = parser.parse_args()

    if should_skip_manual_only_run(args.manual, "run_agent_manual_cases.py"):
        return 0

    container = build_container()
    selected_cases = _resolve_cases(args.cases)

    print("=== 手测文档回归 ===")
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

    _print_generation_probe()

    if not args.skip_budget:
        _run_budget_probe(container)

    if not args.skip_recovery:
        _run_recovery_probe(container)

    _print_manual_only_items()
    return 0


def _resolve_cases(case_ids: list[str] | None) -> list[ManualAgentCase]:
    cases = _build_core_cases()
    if not case_ids:
        return cases
    requested = {item.strip() for item in case_ids if item.strip()}
    return [case for case in cases if case.case_id in requested]


def _build_core_cases() -> list[ManualAgentCase]:
    return [
        ManualAgentCase(
            case_id="series-theme",
            title="3.1 系列主题",
            session_id=_series_session("series-theme"),
            message="这个系列主要讲了哪些主题？要阅读大纲",
            note="对应 docs 3.1，重点看是否先走候选缓冲区，再批量读取 summary。",
        ),
        ManualAgentCase(
            case_id="series-study-path",
            title="3.2 系列学习路径",
            session_id=_series_session("series-study-path"),
            message="这个系列适合怎么学？",
            note="对应 docs 3.2，重点看是否给出学习顺序而不是仅复制标题。",
        ),
        ManualAgentCase(
            case_id="series-role-compare",
            title="3.3 系列角色对比",
            session_id=_series_session("series-role-compare"),
            message="Jmanus 和 AgentScope 在这个系列里分别承担什么角色？",
            note="对应 docs 3.3，重点看是否区分两个框架。",
        ),
        ManualAgentCase(
            case_id="video-seek",
            title="4.1 视频定位",
            session_id=_video_session(VIDEO_ID, "video-seek"),
            message="百度地图 API Key 在视频什么位置提到的？",
            note="对应 docs 4.1，重点看是否先读取完整转写，再发出 video_seek。",
        ),
        ManualAgentCase(
            case_id="open-cards",
            title="4.2 打开知识卡片",
            session_id=_video_session(VIDEO_ID, "open-cards"),
            message="打开知识卡片",
            note="对应 docs 4.2，后端这里只能验证 Agent 是否发出 open_knowledge_cards 动作。",
        ),
        ManualAgentCase(
            case_id="save-note",
            title="4.3 记重点",
            session_id=_video_session(VIDEO_ID, "save-note"),
            message="帮我记一下这个视频的重点",
            note="对应 docs 4.3，后端这里只能验证 save_note / open_notes 动作，前端落库需另看前端用例。",
        ),
        ManualAgentCase(
            case_id="out-of-scope",
            title="7.1 超范围问题",
            session_id=_series_session("out-of-scope"),
            message="帮我写一份旅游攻略",
            note="对应 docs 7.1，重点看是否不调用工作区工具。",
        ),
    ]


def _series_session(tag: str) -> str:
    return f"series|{SERIES_ID}|series-home|{tag}"


def _video_session(video_id: str, tag: str) -> str:
    return f"video|{SERIES_ID}|{video_id}|studio|{tag}"


def _print_case(case: ManualAgentCase, result, *, show_raw_events: bool) -> None:
    print(f"=== [{case.case_id}] {case.title} ===")
    print(f"session_id: {case.session_id}")
    print(f"message: {case.message}")
    if case.note:
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


def _print_generation_probe() -> None:
    summary_missing = _find_video_missing("summary.json")
    mindmap_missing = _find_video_missing("mindmap.json", require_summary=True)

    print("=== 生成类前置探测 ===")
    if mindmap_missing is not None:
        print(f"可用于 5.1 打开导图触发生成的样本: {mindmap_missing}")
    else:
        print("5.1 当前未找到“已有 summary 但缺少 mindmap”的样本。")
    if summary_missing is not None:
        print(f"可用于 5.2 打开概况触发生成的样本: {summary_missing}")
    else:
        print("5.2 当前未找到“缺少 summary”的样本，因此本轮自动回归跳过。")
    print()


def _find_video_missing(file_name: str, *, require_summary: bool = False) -> str | None:
    workspace_root = ROOT / "workspace"
    for series_dir in workspace_root.iterdir():
        if not series_dir.is_dir():
            continue
        for video_dir in series_dir.iterdir():
            if not video_dir.is_dir():
                continue
            if require_summary and not (video_dir / "summary.json").exists():
                continue
            if not (video_dir / file_name).exists():
                return f"{series_dir.name}/{video_dir.name}"
    return None


def _run_budget_probe(container) -> None:
    session_id = _video_session(VIDEO_ID, "budget-probe")
    service = container.get_agent_service()
    budget_service = container.get_agent_context_usage()
    service.clear_session(session_id=session_id, context_override=None)

    messages = [
        "这个视频主要讲了什么？",
        "它的核心问题是什么？",
        "帮我用更通俗的话重述一下",
    ]

    print("=== 10.2 上下文预算专项 ===")
    before = budget_service.inspect(session_id=session_id, context_override=None)
    print(f"初始预算: total={before.estimated_total_tokens}, recent_messages={_source_tokens(before, 'recent_messages')}, workspace_context={_source_tokens(before, 'workspace_context')}")
    for index, message in enumerate(messages, start=1):
        run_agent_case(
            container=container,
            session_id=session_id,
            message=message,
            clear_session=False,
        )
        usage = budget_service.inspect(session_id=session_id, context_override=None)
        print(
            f"第{index}轮后: total={usage.estimated_total_tokens}, "
            f"recent_messages={_source_tokens(usage, 'recent_messages')}, "
            f"level={usage.level}"
        )
    print()


def _run_recovery_probe(container) -> None:
    session_id = _video_session(VIDEO_ID, "recovery-probe")
    service = container.get_agent_service()
    session_store = container.agent_session_store
    service.clear_session(session_id=session_id, context_override=None)

    run_agent_case(
        container=container,
        session_id=session_id,
        message="这个视频主要讲了什么？",
        clear_session=False,
    )
    run_agent_case(
        container=container,
        session_id=session_id,
        message="帮我记一下这个视频重点",
        clear_session=False,
    )

    snapshot = session_store.get_snapshot(session_id)
    print("=== 11.1 会话恢复专项 ===")
    if snapshot is None:
        print("未找到会话快照。")
        print()
        return
    print(f"snapshot_memory_key: {snapshot.memory_key}")
    print(f"snapshot_message_count: {snapshot.message_count}")
    print("snapshot_messages:")
    for item in snapshot.messages[-4:]:
        print(f"  - {item.role}: {item.content}")
    print()


def _source_tokens(usage, source_id: str) -> int:
    for item in usage.sources:
        if item.id == source_id:
            return item.estimated_tokens
    return 0


def _print_manual_only_items() -> None:
    print("=== 仍需前端/人工或前端测试覆盖的项 ===")
    print("- 首页不显示聊天面板、只在 series/video 显示聊天与预算条：这是 UI 展示逻辑，不是后端流式脚本能直接证明的。")
    print("- 右侧是否真的切到知识卡片/视频/导图页，以及视频播放器是否实际跳转：后端只能验证 selected_tool / seek_seconds payload，真实界面仍需前端测试或人工确认。")
    print("- 思路块/工具链块的折叠样式、耗时标签和流式呈现顺序：后端能给事件顺序，但最终渲染效果还要看前端。")
    print("- save_note / generate_overview / generate_mindmap 的前端副作用：当前脚本能验证 Agent 发出了正确动作，真实落库与页面更新要结合前端用例。")
    print()


if __name__ == "__main__":
    raise SystemExit(main())
