from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.context.compact import AgentMemoryCompactionService
from backend.agent.context.semantic_compactor import COMPACTOR_SYSTEM_PROMPT
from backend.agent.memory.store import InMemoryAgentMemoryStore
from backend.agent.schemas.messages import AgentChatMessage


class _CompactionGateway:
    def create_structured_completion(self, messages, response_model):
        del messages, response_model
        raise NotImplementedError

    def create_text_completion_stream(self, messages):
        del messages
        yield ""

    def create_text_completion(self, messages):
        assert COMPACTOR_SYSTEM_PROMPT in messages[0].content
        return (
            '{"summary":"用户希望总结系列主题与学习顺序。",'
            '"confirmed_facts":["需要总结主题","需要补学习顺序"],'
            '"open_threads":["保留主线"],'
            '"constraints":["内容太多时先抓主线"]}'
        )


class AgentContextCompactionTests(unittest.TestCase):
    def test_compacts_older_messages_into_one_system_summary(self) -> None:
        store = InMemoryAgentMemoryStore()
        memory_key = "series|agent-frameworks"
        store.append_messages(
            memory_key,
            [
                AgentChatMessage(role="user", content="请总结这个系列的主要主题和每一讲重点，要详细一些。"),
                AgentChatMessage(role="assistant", content="我会先读取系列内容，再帮你归纳学习路线。"),
                AgentChatMessage(role="user", content="还要补充一下每一讲之间的关系。"),
                AgentChatMessage(role="assistant", content="好的，我会把关系链也整理出来。"),
                AgentChatMessage(role="user", content="如果内容太多，就先抓主线。"),
                AgentChatMessage(role="assistant", content="明白，优先保留主线。"),
                AgentChatMessage(role="user", content="最后再帮我做一个学习顺序建议。"),
                AgentChatMessage(role="assistant", content="可以，我会在结尾补上建议。"),
            ],
        )

        compacted = AgentMemoryCompactionService(
            gateway=_CompactionGateway(),
            memory_store=store,
            context_window_tokens=40,
            compact_threshold_ratio=1.0,
            keep_tail_messages=4,
        ).compact_if_needed(memory_key)

        self.assertTrue(compacted)
        messages = store.get_messages(memory_key)
        self.assertEqual(len(messages), 5)
        self.assertEqual(messages[0].role, "system")
        self.assertIn("压缩摘要", messages[0].content)
        self.assertIn("用户希望总结系列主题与学习顺序", messages[0].content)
        self.assertIn("已确认事实", messages[0].content)
        self.assertIn("待继续事项", messages[0].content)
        self.assertEqual(messages[-1].content, "可以，我会在结尾补上建议。")


if __name__ == "__main__":
    unittest.main()
