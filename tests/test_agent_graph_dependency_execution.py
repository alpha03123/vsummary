from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.runtime.graph import build_agent_graph
from backend.agent_graph.query.models import CompareSplitDecision, StructuredQueryPlan


class _Classifier:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "", history_summary: str = "", history_selected_videos=None):
        del user_message, scope_type, series_id, video_id, history_summary, history_selected_videos
        return StructuredQueryPlan(goal="action", target_source="all", context_need="chunk", reason="动作", action_name="open_notes")


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _ActionDispatcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def dispatch(self, *, scope_type: str, series_id: str, video_id: str, action_name: str, action_args: dict[str, object]):
        del scope_type, series_id, video_id, action_args
        self.calls.append(action_name)
        return {"direct_response": action_name, "tool_results": [{"tool_name": action_name, "status": "ok", "payload": {}}]}


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        raise AssertionError(f"action path should not hit answer: {user_message}, {retrieval_results}, {meta_state}")


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphDependencyExecutionTests(unittest.TestCase):
    def test_graph_finishes_after_single_action_without_task_loop(self) -> None:
        dispatcher = _ActionDispatcher()
        graph = build_agent_graph(
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            action_dispatcher=dispatcher,
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "打开笔记",
            }
        )

        self.assertEqual(dispatcher.calls, ["open_notes"])
        self.assertEqual(result["assistant_message"], "open_notes")


if __name__ == "__main__":
    unittest.main()
