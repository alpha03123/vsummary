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
    def run(
        self,
        *,
        user_message: str,
        scope_type: str,
        series_id: str,
        video_id: str = "",
        history_summary: str = "",
        history_selected_videos=None,
    ):
        del user_message, scope_type, series_id, video_id, history_summary, history_selected_videos
        return StructuredQueryPlan(goal="understand", target_source="summary", context_need="chunk", reason="概括。")


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _Retrieval:
    def search(self, **kwargs):
        del kwargs
        return {"hits": [{"video_id": "video-1", "source_type": "summary", "snippet": "这是重点摘要。"}]}


class _MetaStateReader:
    def read(self, **kwargs):
        del kwargs
        return {}


class _ActionDispatcher:
    def dispatch(self, **kwargs):
        del kwargs
        return {"direct_response": "", "tool_results": []}


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, meta_state
        return f"总结：{retrieval_results[0]['snippet']}"


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del task_outputs
        return f"{history_summary} | 用户问：{user_message} | 结果：{assistant_message}".strip(" |")


class AgentGraphMemoryFlowTests(unittest.TestCase):
    def test_finalize_then_update_memory_node_produces_summary_update(self) -> None:
        graph = build_agent_graph(
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "总结一下这节内容",
                "history_summary": "之前一直在讨论 AK",
            }
        )

        self.assertIn("之前一直在讨论 AK", result["history_summary_update"])
        self.assertIn("总结一下这节内容", result["history_summary_update"])
        self.assertIn("总结：这是重点摘要。", result["history_summary_update"])


if __name__ == "__main__":
    unittest.main()
