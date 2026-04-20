from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.runtime.graph import build_series_agent_graph
from backend.agent_graph.query.models import CompareSplitDecision, DecomposeDecision, SeriesQueryDecision


class _Decomposer:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = ""):
        del user_message, scope_type, series_id, video_id
        return DecomposeDecision(
            tasks=[
                {"task_id": "task-2", "instruction": "保存笔记", "depends_on": ["task-1"], "kind_hint": "action"},
                {"task_id": "task-1", "instruction": "总结重点", "depends_on": [], "kind_hint": "understand"},
                {"task_id": "task-3", "instruction": "打开笔记", "depends_on": ["task-2"], "kind_hint": "action"},
            ],
            reason="依赖顺序不等于列表顺序。",
        )


class _Classifier:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "", history_summary: str = "", history_selected_videos=None):
        del scope_type, series_id, video_id, history_summary, history_selected_videos
        if user_message == "总结重点":
            return SeriesQueryDecision(goal="understand", target_source="summary", context_need="chunk", reason="概括")
        if user_message == "保存笔记":
            return SeriesQueryDecision(goal="action", target_source="all", context_need="chunk", reason="保存", action_name="save_note", action_args={})
        return SeriesQueryDecision(goal="action", target_source="all", context_need="chunk", reason="打开", action_name="open_notes", action_args={})


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _Retrieval:
    def search(self, **kwargs):
        del kwargs
        return {"hits": [{"video_id": "video-1", "source_type": "summary", "snippet": "总结结果"}]}


class _MetaStateReader:
    def read(self, **kwargs):
        del kwargs
        return {}


class _ActionDispatcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def dispatch(self, *, scope_type: str, series_id: str, video_id: str, action_name: str, action_args: dict[str, object]):
        del scope_type, series_id, video_id, action_args
        self.calls.append(action_name)
        return {"direct_response": action_name, "tool_results": [{"tool_name": action_name, "status": "ok", "payload": {}}]}


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, meta_state
        return retrieval_results[0]["snippet"]


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphDependencyExecutionTests(unittest.TestCase):
    def test_graph_executes_tasks_by_dependency_not_list_order(self) -> None:
        dispatcher = _ActionDispatcher()
        graph = build_series_agent_graph(
            decomposer_program=_Decomposer(),
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=dispatcher,
            answer_program=_Answer(),
            memory_update_program=_MemoryUpdater(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "先总结，再保存，再打开",
            }
        )

        self.assertEqual(dispatcher.calls, ["save_note", "open_notes"])
        self.assertEqual(
            [item["task_id"] for item in result["task_outputs"]],
            ["task-1", "task-2", "task-3"],
        )


if __name__ == "__main__":
    unittest.main()
