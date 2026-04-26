from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.infrastructure.context_loader import StaticAgentContextLoader
from backend.agent.memory.context import AgentContext
from backend.agent.session.store import FileAgentSessionStore
from backend.agent_graph.runtime.service import AgentGraphService


class _FakeGraph:
    def invoke(self, payload):
        history = payload.get("history_messages", [])
        dialog_history = payload.get("dialog_history", "")
        history_selected_videos = payload.get("history_selected_videos", [])
        return {
            **payload,
            "answer": f"hist={len(history)} dialog={dialog_history} selected={len(history_selected_videos)}",
            "query_plan": {
                "selected_videos": [
                    {"video_id": "1-6", "reason_for_selection": "上一轮选中的 JManus"}
                ]
            },
        }


class _Compactor:
    def __init__(self) -> None:
        self.calls = 0

    def compact_if_needed(self, messages):
        self.calls += 1
        return "压缩后的对话记忆"


class AgentGraphMemoryTests(unittest.TestCase):
    def test_run_turn_loads_history_and_updates_dialog_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileAgentSessionStore(Path(temp_dir))
            context = AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            )
            store.append_turn(
                session_id="series|series-a|series-home",
                memory_key="series|series-a|series-home",
                context=context,
                user_message="先比较 Jmanus 和 AgentScope",
                assistant_message="前面已经比较过一轮。",
                tool_results=[],
            )

            service = AgentGraphService(
                context_loader=StaticAgentContextLoader(context),
                graph=_FakeGraph(),
                session_store=store,
            )

            result = service.run_turn(
                session_id="series|series-a|series-home",
                user_message="那 Jmanus 好在哪里？",
            )

            self.assertIn("hist=2", result.assistant_message)
            self.assertIn("selected=0", result.assistant_message)
            snapshot = store.get_snapshot("series|series-a|series-home")
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertIn("先比较 Jmanus 和 AgentScope", snapshot.context.dialog_history)
            self.assertIn("那 Jmanus 好在哪里？", snapshot.context.dialog_history)
            self.assertEqual(snapshot.selected_videos[0].video_id, "1-6")

            result = service.run_turn(
                session_id="series|series-a|series-home",
                user_message="那 AgentScope 呢？",
            )
            self.assertIn("selected=1", result.assistant_message)

    def test_run_turn_compresses_dialog_history_only_after_ninety_percent_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileAgentSessionStore(Path(temp_dir))
            compactor = _Compactor()
            long_text = "A" * 400
            context = AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
                dialog_history=long_text,
                evidence_history={"video_summary": {"video_id": "video-1"}},
            )
            store.append_turn(
                session_id="series|series-a|series-home",
                memory_key="series|series-a|series-home",
                context=context,
                user_message=long_text,
                assistant_message=long_text,
                tool_results=[],
            )

            service = AgentGraphService(
                context_loader=StaticAgentContextLoader(context),
                graph=_FakeGraph(),
                session_store=store,
                dialog_history_compactor=compactor,
            )

            service.run_turn(
                session_id="series|series-a|series-home",
                user_message=long_text,
            )

            snapshot = store.get_snapshot("series|series-a|series-home")
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(snapshot.context.dialog_history, "压缩后的对话记忆")
            self.assertEqual(snapshot.context.evidence_history, {"video_summary": {"video_id": "video-1"}})
            self.assertEqual(compactor.calls, 1)


if __name__ == "__main__":
    unittest.main()
