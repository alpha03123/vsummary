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
                {"task_id": "task-1", "instruction": "总结重点", "depends_on": [], "kind_hint": "understand"},
                {"task_id": "task-2", "instruction": "保存笔记", "depends_on": ["task-1"], "kind_hint": "action"},
                {"task_id": "task-3", "instruction": "打开笔记", "depends_on": ["task-2"], "kind_hint": "action"},
            ],
            reason="这是一个三步复合任务。",
        )


class _Classifier:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "", history_summary: str = "", history_selected_videos=None):
        del scope_type, series_id, video_id, history_summary, history_selected_videos
        if user_message == "总结重点":
            return SeriesQueryDecision(goal="understand", target_source="summary", context_need="chunk", reason="先总结。")
        if user_message == "保存笔记":
            return SeriesQueryDecision(
                goal="action",
                target_source="all",
                context_need="chunk",
                reason="保存动作。",
                action_name="save_note",
                action_args={},
            )
        return SeriesQueryDecision(
            goal="action",
            target_source="all",
            context_need="chunk",
            reason="打开动作。",
            action_name="open_notes",
            action_args={},
        )


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _Retrieval:
    def search(self, **kwargs):
        return {
            "hits": [
                {
                    "video_id": kwargs.get("video_id", "video-1") or "video-1",
                    "title": "Video 1",
                    "source_type": "summary",
                    "snippet": "这里是总结依据。",
                }
            ]
        }


class _MetaStateReader:
    def read(self, **kwargs):
        del kwargs
        return {}


class _ActionDispatcher:
    def dispatch(self, *, scope_type: str, series_id: str, video_id: str, action_name: str, action_args: dict[str, object]):
        del scope_type, series_id, video_id
        messages = {
            "save_note": "我已经帮你记好这条笔记。",
            "open_notes": "我已经帮你打开笔记工具。",
        }
        if action_name == "save_note":
            assert action_args["note_content"] == "总结：这里是总结依据。"
        return {
            "direct_response": messages[action_name],
            "tool_results": [{"tool_name": action_name, "status": "ok", "payload": action_args}],
        }


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, meta_state
        return f"总结：{retrieval_results[0]['snippet']}"


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphMultitaskFlowTests(unittest.TestCase):
    def test_multitask_flow_executes_all_subtasks_and_finalizes(self) -> None:
        graph = build_series_agent_graph(
            decomposer_program=_Decomposer(),
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
            memory_update_program=_MemoryUpdater(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "先总结重点，再保存笔记，再打开笔记",
            }
        )

        self.assertEqual(len(result["task_outputs"]), 3)
        self.assertIn("总结：", result["assistant_message"])
        self.assertIn("打开笔记", result["assistant_message"])


if __name__ == "__main__":
    unittest.main()
