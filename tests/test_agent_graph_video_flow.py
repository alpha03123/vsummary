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
    def __init__(self, decision: StructuredQueryPlan) -> None:
        self._decision = decision

    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "", history_summary: str = "", history_selected_videos=None):
        del user_message, scope_type, series_id, video_id, history_summary, history_selected_videos
        return self._decision


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        return CompareSplitDecision(queries=[])


class _Retrieval:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "scope_type": kwargs["scope_type"],
            "series_id": kwargs["series_id"],
            "video_id": kwargs.get("video_id", ""),
            "query": kwargs["query"],
            "target_source": kwargs["target_source"],
            "source_tags": list(kwargs.get("source_tags", [])),
            "hits": [
                {
                    "video_id": kwargs.get("video_id", "video-1") or "video-1",
                    "title": "Video 1",
                    "source_type": "transcript_chunk"
                    if "transcript" in kwargs.get("source_tags", []) or kwargs["target_source"] == "transcript"
                    else "summary",
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


class _PinpointService:
    def locate(self, *, series_id: str, video_id: str, query: str):
        return (
            {
                "video_id": video_id,
                "title": "Video 1",
                "query": query,
                "matches": [
                    {
                        "start_seconds": 32.0,
                        "end_seconds": 36.0,
                        "text": "这里提到了 AK。",
                    }
                ],
                "best_match": {
                    "start_seconds": 32.0,
                    "end_seconds": 36.0,
                    "text": "这里提到了 AK。",
                },
                "transcript_missing": False,
            },
            [
                {
                    "tool_name": "get_video_transcript",
                    "status": "ok",
                    "payload": {"video_id": video_id, "title": "Video 1", "match_count": 1},
                },
                {
                    "tool_name": "video_seek",
                    "status": "ok",
                    "payload": {"video_id": video_id, "seek_seconds": 32.0, "match_end_seconds": 36.0, "matched_text": "这里提到了 AK。"},
                },
            ],
        )


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message
        if meta_state:
            return f"meta:{meta_state['overview']['status']}"
        return "answer:" + ",".join(
            str(item.get("source_type", ""))
            for item in retrieval_results
        )


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphVideoFlowTests(unittest.TestCase):
    def test_video_summary_flow_retrieves_summary(self) -> None:
        retrieval = _Retrieval()
        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
                    goal="understand",
                    target_source="summary",
                    context_need="chunk",
                    reason="视频概括问题。",
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=retrieval,
            meta_state_reader=_MetaStateReader(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "这个视频主要讲了什么？",
                "evidence_history": {
                    "video_summary": {
                        "video_id": "video-1",
                        "title": "Video 1",
                        "summary": {
                            "one_sentence_summary": "这是当前视频的摘要。",
                            "core_problem": "视频讲解 OpenManus。",
                            "key_takeaways": ["OpenManus 是开源框架。"],
                            "chapters": [],
                        },
                    }
                },
            }
        )

        self.assertEqual(result["query_plan"]["goal"], "understand")
        self.assertEqual(result["query_plan"]["candidate_video_ids"], ["video-1"])
        self.assertEqual(result["query_plan"]["selected_videos"][0]["video_id"], "video-1")
        self.assertEqual(result["query_plan"]["subplans"][0]["depth"], "summary")
        self.assertEqual(result["retrieval_results"][0]["depth"], "summary")
        self.assertEqual(result["retrieval_results"][0]["items"][0]["source_type"], "summary")
        self.assertEqual(result["answer"], "answer:summary")
        self.assertEqual(retrieval.calls, [])

    def test_video_content_flow_uses_unified_rag_tags_after_summary(self) -> None:
        retrieval = _Retrieval()
        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
                    goal="understand",
                    target_source="all",
                    context_need="chunk",
                    reason="视频内容问题，需要补充检索。",
                )
            ),
            compare_split_program=_Splitter(),
            retrieval_service=retrieval,
            meta_state_reader=_MetaStateReader(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "video|series-a|video-1|overview",
                "scope_type": "video",
                "series_id": "series-a",
                "video_id": "video-1",
                "user_message": "OpenManus 是啥，它和当前视频里别的框架啥关系？",
                "evidence_history": {
                    "video_summary": {
                        "video_id": "video-1",
                        "title": "Video 1",
                        "summary": {
                            "one_sentence_summary": "这是当前视频的摘要。",
                            "core_problem": "视频讲解 OpenManus。",
                            "key_takeaways": ["OpenManus 是开源框架。"],
                            "chapters": [],
                        },
                    }
                },
            }
        )

        self.assertEqual(result["query_plan"]["subplans"][0]["depth"], "summary")
        self.assertEqual(result["query_plan"]["subplans"][1]["depth"], "video_rag")
        self.assertEqual(result["query_plan"]["subplans"][1]["retrieval_tags"], ["summary", "transcript", "notes", "cards"])
        self.assertEqual(result["query_plan"]["candidate_video_ids"], ["video-1"])
        self.assertEqual(result["retrieval_results"][0]["depth"], "summary")
        self.assertEqual(result["retrieval_results"][1]["depth"], "video_rag")
        self.assertEqual(result["retrieval_results"][1]["items"][0]["source_type"], "transcript_chunk")
        self.assertEqual(result["answer"], "answer:summary,transcript_chunk")
        self.assertEqual(retrieval.calls[0]["source_tags"], ["summary", "transcript", "notes", "cards"])

    def test_video_meta_state_flow_reads_structured_state(self) -> None:
        graph = build_agent_graph(
            classifier_program=_Classifier(
                StructuredQueryPlan(
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
        self.assertEqual(result["assistant_message"], "meta:ready")


if __name__ == "__main__":
    unittest.main()
