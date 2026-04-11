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
    def __init__(self, decision: SeriesQueryDecision) -> None:
        self._decision = decision

    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = ""):
        del user_message, scope_type, series_id, video_id
        return self._decision


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _Retrieval:
    def search(self, **kwargs):
        return {
            "scope_type": kwargs["scope_type"],
            "series_id": kwargs["series_id"],
            "video_id": kwargs.get("video_id", ""),
            "query": kwargs["query"],
            "target_source": kwargs["target_source"],
            "hits": [
                {
                    "video_id": kwargs.get("video_id", "video-1") or "video-1",
                    "title": "Video 1",
                    "source_type": "transcript_chunk" if kwargs["target_source"] == "transcript" else "summary",
                    "snippet": "这里是命中内容。",
                }
            ],
        }


class _MetaStateReader:
    def read(self, **kwargs):
        return {
            "scope_type": kwargs["scope_type"],
            "series_id": kwargs["series_id"],
            "video_id": kwargs.get("video_id", ""),
            "overview": {"generated": True, "status": "ready"},
            "mindmap": {"generated": False, "status": "pending"},
        }


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message
        if meta_state:
            return f"meta:{meta_state['overview']['status']}"
        return f"answer:{retrieval_results[0]['source_type']}"


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphVideoFlowTests(unittest.TestCase):
    def test_video_summary_flow_retrieves_summary(self) -> None:
        graph = build_series_agent_graph(
            decomposer_program=_Decomposer(),
            classifier_program=_Classifier(
                SeriesQueryDecision(
                    goal="understand",
                    target_source="summary",
                    context_need="chunk",
                    reason="视频概括问题。",
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            answer_program=_Answer(),
            memory_update_program=_MemoryUpdater(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "这个视频主要讲了什么？",
            }
        )

        self.assertEqual(result["query_plan"]["goal"], "understand")
        self.assertEqual(result["retrieval_results"][0]["source_type"], "summary")
        self.assertEqual(result["answer"], "answer:summary")

    def test_video_locate_flow_retrieves_transcript(self) -> None:
        graph = build_series_agent_graph(
            decomposer_program=_Decomposer(),
            classifier_program=_Classifier(
                SeriesQueryDecision(
                    goal="locate",
                    target_source="transcript",
                    context_need="chunk",
                    reason="视频定位问题。",
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            answer_program=_Answer(),
            memory_update_program=_MemoryUpdater(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "视频里哪里提到了 AK？",
            }
        )

        self.assertEqual(result["retrieval_results"][0]["source_type"], "transcript_chunk")
        self.assertEqual(result["answer"], "answer:transcript_chunk")

    def test_video_meta_state_flow_reads_structured_state(self) -> None:
        graph = build_series_agent_graph(
            decomposer_program=_Decomposer(),
            classifier_program=_Classifier(
                SeriesQueryDecision(
                    goal="meta_state",
                    target_source="all",
                    context_need="chunk",
                    reason="视频资源状态问题。",
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            meta_state_reader=_MetaStateReader(),
            answer_program=_Answer(),
            memory_update_program=_MemoryUpdater(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "这个视频有哪些工具已经生成了？",
            }
        )

        self.assertEqual(result["meta_state"]["overview"]["status"], "ready")
        self.assertEqual(result["answer"], "meta:ready")


if __name__ == "__main__":
    unittest.main()
