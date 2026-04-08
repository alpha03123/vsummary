from __future__ import annotations

import argparse
import sys
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agent_regression_utils import build_container
from backend.agent.context.compact import AgentMemoryCompactionService
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.schemas.messages import AgentChatMessage


def main() -> int:
    parser = argparse.ArgumentParser(description="真实模型压缩大量历史消息，检查语义压缩质量。")
    parser.add_argument("--window-tokens", type=int, default=12000)
    parser.add_argument("--compact-threshold-ratio", type=float, default=0.8)
    parser.add_argument("--keep-tail-messages", type=int, default=6)
    parser.add_argument("--turns", type=int, default=18)
    args = parser.parse_args()

    container = build_container()
    gateway = container.get_agent_service()._gateway
    memory_store = InMemoryAgentMemoryStore()
    memory_key = "probe|semantic-compaction"
    messages = _build_probe_messages(args.turns)
    memory_store.append_messages(memory_key, messages)

    before_tokens = _estimate_messages_tokens(messages)
    compacted = AgentMemoryCompactionService(
        gateway=gateway,
        memory_store=memory_store,
        context_window_tokens=args.window_tokens,
        compact_threshold_ratio=args.compact_threshold_ratio,
        keep_tail_messages=args.keep_tail_messages,
    ).compact_if_needed(memory_key)
    after_messages = memory_store.get_messages(memory_key)
    after_tokens = _estimate_messages_tokens(after_messages)

    print("=== semantic-compaction-probe ===")
    print(f"turns: {args.turns}")
    print(f"before_message_count: {len(messages)}")
    print(f"before_estimated_tokens: {before_tokens}")
    print(f"compacted: {compacted}")
    print(f"after_message_count: {len(after_messages)}")
    print(f"after_estimated_tokens: {after_tokens}")
    print()
    print("=== compacted_summary ===")
    if after_messages:
        print(after_messages[0].content)
    print()
    print("=== preserved_tail ===")
    for item in after_messages[-args.keep_tail_messages:]:
        print(f"[{item.role}] {item.content}")
    return 0


def _build_probe_messages(turns: int) -> list[AgentChatMessage]:
    messages: list[AgentChatMessage] = []
    for index in range(1, turns + 1):
        messages.append(
            AgentChatMessage(
                role="user",
                content=(
                    f"第{index}轮问题：请继续整理 Agent Frameworks 系列的学习材料。"
                    f"这轮重点是比较 JManus、AgentScope、Nacos 3、ReAct 之间的关系，"
                    f"并且记住我偏好用 Java 生态视角理解，不要用 Python 社区术语带偏。"
                    f"另外，把已经确认的内容和还没确认的内容分开写，避免装作已经读过全文。"
                ),
            )
        )
        messages.append(
            AgentChatMessage(
                role="assistant",
                content=(
                    f"第{index}轮回答：当前已确认的信息包括："
                    "JManus 是面向 Java 的多智能体协作框架；"
                    "AgentScope 更强调自主代理与 ReAct；"
                    "Nacos 3 在课程里承担服务发现与元数据管理角色；"
                    "ReAct 是推理-行动-验证-再推理循环。"
                    "未确认的细节我会继续保持保守表达。"
                    "你还要求我后续如果证据不足，就优先说“当前证据范围内”，不要夸大。"
                ),
            )
        )
    return messages


def _estimate_messages_tokens(messages: list[AgentChatMessage]) -> int:
    text = "\n".join(f"{message.role}:{message.content}" for message in messages).strip()
    if not text:
        return 0
    return max(1, ceil(len(text.encode("utf-8")) / 3))


if __name__ == "__main__":
    raise SystemExit(main())
