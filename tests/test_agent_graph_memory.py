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
from backend.agent_graph.service import AgentGraphService


class _FakeGraph:
    def invoke(self, payload):
        history = payload.get("history_messages", [])
        history_summary = payload.get("history_summary", "")
        history_selected_videos = payload.get("history_selected_videos", [])
        return {
            **payload,
            "answer": f"hist={len(history)} summary={history_summary} selected={len(history_selected_videos)}",
            "history_summary_update": "本轮继续围绕 Jmanus 做比较。",
            "query_plan": {
                "selected_videos": [
                    {"video_id": "1-6", "reason_for_selection": "上一轮选中的 JManus"}
                ]
            },
        }


class AgentGraphMemoryTests(unittest.TestCase):
    def test_run_turn_loads_history_and_updates_summary(self) -> None:
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
            self.assertEqual(snapshot.context.compact_summary, "本轮继续围绕 Jmanus 做比较。")
            self.assertEqual(snapshot.selected_videos[0].video_id, "1-6")

            result = service.run_turn(
                session_id="series|series-a|series-home",
                user_message="那 AgentScope 呢？",
            )
            self.assertIn("selected=1", result.assistant_message)


if __name__ == "__main__":
    unittest.main()
