import argparse
import json
from agent_regression_utils import build_container, run_agent_case, should_skip_manual_only_run


def main() -> int:
    parser = argparse.ArgumentParser(description="手动运行低优先级的真实 Agent series 回复回归。")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="显式确认本次要运行真实模型对话回归；默认跳过。",
    )
    parser.add_argument(
        "--session-id",
        default="series|agent-frameworks|series-home",
        help="Agent session_id，默认使用 agent-frameworks 系列首页。",
    )
    parser.add_argument(
        "--message",
        default="系列主要讲了哪些主题？要阅读大纲",
        help="要发送给 Agent 的真实问题。",
    )
    parser.add_argument(
        "--keep-session",
        action="store_true",
        help="保留已有会话快照；默认每次运行前先清空会话。",
    )
    parser.add_argument(
        "--show-raw-events",
        action="store_true",
        help="额外打印完整事件 JSON。",
    )
    args = parser.parse_args()

    if should_skip_manual_only_run(args.manual, "run_agent_series_reply.py"):
        return 0

    result = run_agent_case(
        container=build_container(),
        session_id=args.session_id,
        message=args.message,
        clear_session=not args.keep_session,
    )

    print("=== Agent Series Reply ===")
    print(f"session_id: {args.session_id}")
    print(f"message: {args.message}")
    print()

    print("=== 思路摘要 ===")
    if result.thinking_summaries:
        for index, summary in enumerate(result.thinking_summaries, start=1):
            print(f"[{index}] {summary}")
    else:
        print("(无)")
    print()

    print("=== 工具轨迹 ===")
    if result.tool_rows:
        for row in result.tool_rows:
            print(row)
    else:
        print("(无)")
    print()

    print("=== 最终回答 ===")
    print(result.final_answer or "(空)")

    if args.show_raw_events:
        print()
        print("=== 原始事件 ===")
        print(json.dumps(result.raw_events, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
