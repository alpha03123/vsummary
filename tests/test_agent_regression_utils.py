from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.schemas.stream_events import AgentStreamEvent
from scripts.agent_regression_utils import run_agent_case


class _FakeService:
    def clear_session(self, *, session_id: str, context_override=None) -> None:
        del session_id, context_override

    def stream_with_context(self, *, session_id: str, user_message: str, context_override=None, debug_trace=None):
        del session_id, user_message, context_override
        if debug_trace is not None:
            debug_trace["graph_result"] = {"answer": "ok"}
        yield AgentStreamEvent(type="thinking_completed", payload={"summary": "已完成思考"})
        yield AgentStreamEvent(type="tool_completed", payload={"tool_name": "get_video_summary", "status": "ok", "payload": {"title": "Video 1"}})
        yield AgentStreamEvent(type="answer_completed", payload={"message": "最终回答"})


class _FakeContainer:
    def get_agent_service(self):
        return _FakeService()


class AgentRegressionUtilsTests(unittest.TestCase):
    def test_run_agent_case_returns_debug_trace_and_elapsed_ms(self) -> None:
        result = run_agent_case(
            container=_FakeContainer(),
            session_id="series|series-a|series-home",
            message="这个系列主要讲了什么？",
            clear_session=True,
        )

        self.assertEqual(result.thinking_summaries, ["已完成思考"])
        self.assertEqual(result.final_answer, "最终回答")
        self.assertIn("graph_result", result.debug_trace)
        self.assertTrue(result.raw_events)
        self.assertTrue(all("elapsed_ms" in item for item in result.raw_events))


if __name__ == "__main__":
    unittest.main()
