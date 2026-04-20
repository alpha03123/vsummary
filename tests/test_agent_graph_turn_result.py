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
from backend.agent.schemas.action_plan import AgentTurnResult
from backend.agent.session.store import FileAgentSessionStore
from backend.agent_graph.runtime.service import AgentGraphService


class _FakeGraph:
    def invoke(self, payload):
        return {
            **payload,
            "query_plan": {"goal": "understand"},
            "answer": "graph answer",
            "retrieval_results": [{"video_id": "video-1", "source_type": "summary"}],
        }


class AgentGraphTurnResultTests(unittest.TestCase):
    def test_run_turn_returns_agent_turn_result_and_persists_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileAgentSessionStore(Path(temp_dir))
            service = AgentGraphService(
                context_loader=StaticAgentContextLoader(
                    AgentContext(
                        session_id="video|series-a|video-1|overview",
                        scope_type="video",
                        series_id="series-a",
                        video_id="video-1",
                    )
                ),
                graph=_FakeGraph(),
                session_store=store,
            )

            result = service.run_turn(
                session_id="video|series-a|video-1|overview",
                user_message="这个视频主要讲了什么？",
            )

            self.assertIsInstance(result, AgentTurnResult)
            self.assertEqual(result.assistant_message, "graph answer")
            snapshot = store.get_snapshot("video|series-a|video-1|overview")
            self.assertIsNotNone(snapshot)


if __name__ == "__main__":
    unittest.main()
