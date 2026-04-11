from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.graph import build_series_agent_graph
from backend.agent_graph.models import CompareSplitDecision, DecomposeDecision, SeriesQueryDecision


class _Decomposer:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = ""):
        del scope_type, series_id, video_id
        return DecomposeDecision(
            tasks=[{"task_id": "task-1", "instruction": user_message, "depends_on": [], "kind_hint": ""}],
            reason="单任务。",
        )


class _Classifier:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = ""):
        del user_message, scope_type, series_id, video_id
        return SeriesQueryDecision(
            goal="locate",
            target_source="transcript",
            context_need="chunk",
            reason="定位问题。",
        )


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _Retrieval:
    def search(self, **kwargs):
        return {
            "series_id": kwargs["series_id"],
            "query": kwargs["query"],
            "target_source": kwargs["target_source"],
            "hits": [
                {
                    "video_id": "1-5",
                    "title": "安装 Nacos 3",
                    "source_type": "transcript_chunk",
                    "snippet": "这里讲 Nacos 3。",
                }
            ],
        }


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, meta_state
        return f"命中 {retrieval_results[0]['video_id']}"


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphSeriesFlowTests(unittest.TestCase):
    def test_series_locate_flow_runs_classify_then_retrieve_then_answer(self) -> None:
        graph = build_series_agent_graph(
            decomposer_program=_Decomposer(),
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            answer_program=_Answer(),
            memory_update_program=_MemoryUpdater(),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-a|home",
                "scope_type": "series",
                "series_id": "series-a",
                "user_message": "这个系列里哪里讲过 Nacos 3？",
            }
        )

        self.assertEqual(result["query_plan"]["goal"], "locate")
        self.assertTrue(result["retrieval_results"])
        self.assertIn("1-5", result["answer"])


if __name__ == "__main__":
    unittest.main()
