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
        return StructuredQueryPlan(
            goal="locate",
            target_source="transcript",
            context_need="chunk",
            reason="定位问题。",
        )


class _ClassifierWithStructuredPlan:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = "", history_summary: str = "", history_selected_videos=None):
        del user_message, scope_type, series_id, video_id, history_summary, history_selected_videos
        return StructuredQueryPlan(
            goal="locate",
            target_source="transcript",
            context_need="chunk",
            reason="定位问题。",
            candidate_video_ids=["1-5"],
            selected_videos=[
                {"video_id": "1-5", "reason_for_selection": "安装 Nacos 3 的目标视频。"}
            ],
            subplans=[
                {
                    "target_video_ids": ["1-5"],
                    "depth": "video_graph",
                    "query": "定位 Docker 安装 Nacos 3 的时间点",
                }
            ],
        )


class _CapturingClassifier:
    def __init__(self) -> None:
        self.kwargs = None

    def run(self, **kwargs):
        self.kwargs = kwargs
        return StructuredQueryPlan(
            goal="understand",
            target_source="summary",
            context_need="chunk",
            reason="capture",
        )


class _CapturingSeriesPlanner:
    def __init__(self, plan: dict[str, object]) -> None:
        self.plan = plan
        self.kwargs = None

    def create_plan(self, **kwargs):
        self.kwargs = kwargs
        return self.plan


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


class _PinpointService:
    def locate(self, *, series_id: str, video_id: str, query: str):
        return (
            {
                "video_id": video_id,
                "title": "安装 Nacos 3",
                "query": query,
                "matches": [
                    {
                        "start_seconds": 20.05,
                        "end_seconds": 24.05,
                        "text": "这里我是以Docker的方式去安装Neckers",
                    }
                ],
                "best_match": {
                    "start_seconds": 20.05,
                    "end_seconds": 24.05,
                    "text": "这里我是以Docker的方式去安装Neckers",
                },
                "transcript_missing": False,
            },
            [
                {
                    "tool_name": "get_video_transcript",
                    "status": "ok",
                    "payload": {"video_id": video_id, "title": "安装 Nacos 3", "match_count": 1},
                },
                {
                    "tool_name": "video_seek",
                    "status": "ok",
                    "payload": {"video_id": video_id, "seek_seconds": 20.05},
                },
            ],
        )


class _Answer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        del user_message, meta_state
        return f"命中 {retrieval_results[0]['video_id']}"


class _ExplodingAnswer:
    def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
        raise AssertionError(
            f"series content path should not call generic answer program: "
            f"user_message={user_message}, retrieval_results={retrieval_results}, meta_state={meta_state}"
        )


class _SeriesAggregator:
    def run(self, *, user_message: str, query_plan: dict[str, object], execution_results: list[dict[str, object]], tool_results: list[dict[str, object]], dialog_history: str = "", history_messages=None, debug_trace=None):
        del user_message, tool_results, dialog_history, history_messages, debug_trace
        return (
            f"聚合:selected={','.join(query_plan.get('candidate_video_ids', []))};"
            f"results={len(execution_results)};"
            f"first_depth={execution_results[0]['depth']}"
        )


class _ActionDispatcher:
    def dispatch(self, *, scope_type: str, series_id: str, video_id: str, action_name: str, action_args: dict[str, object]):
        del scope_type, series_id, video_id, action_args
        return {
            "message": "已打开笔记",
            "tool_results": [{"tool_name": action_name, "status": "ok", "payload": {}}],
        }


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class AgentGraphSeriesFlowTests(unittest.TestCase):
    def test_series_locate_flow_runs_classify_then_retrieve_then_answer(self) -> None:
        graph = build_agent_graph(
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            pinpoint_service=_PinpointService(),
            answer_program=_Answer(),
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
        self.assertEqual(result["query_plan"]["subplans"][0]["depth"], "video_graph")
        self.assertEqual(result["query_plan"]["candidate_video_ids"], ["1-5"])
        self.assertEqual(result["query_plan"]["selected_videos"][0]["video_id"], "1-5")
        self.assertEqual(result["query_plan"]["subplans"][0]["target_video_ids"], ["1-5"])
        self.assertTrue(result["retrieval_results"])
        self.assertIn("1-5", result["answer"])
        self.assertEqual(result["tool_results"][0]["tool_name"], "get_video_transcript")
        self.assertEqual(result["tool_results"][1]["tool_name"], "video_seek")

    def test_series_locate_flow_keeps_classifier_supplied_structured_plan(self) -> None:
        graph = build_agent_graph(
            classifier_program=_ClassifierWithStructuredPlan(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            pinpoint_service=_PinpointService(),
            answer_program=_Answer(),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-a|home",
                "scope_type": "series",
                "series_id": "series-a",
                "user_message": "这个系列里哪里讲过 Nacos 3？",
            }
        )

        self.assertEqual(result["query_plan"]["candidate_video_ids"], ["1-5"])
        self.assertEqual(result["query_plan"]["selected_videos"][0]["reason_for_selection"], "安装 Nacos 3 的目标视频。")
        self.assertEqual(result["query_plan"]["subplans"][0]["query"], "定位 Docker 安装 Nacos 3 的时间点")

    def test_build_plan_passes_history_selection_context_to_classifier(self) -> None:
        classifier = _CapturingClassifier()
        graph = build_agent_graph(
            classifier_program=classifier,
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            pinpoint_service=_PinpointService(),
            answer_program=_Answer(),
        )

        graph.invoke(
            {
                "session_id": "series|series-a|home",
                "scope_type": "series",
                "series_id": "series-a",
                "user_message": "继续比较它们的定位差异",
                "history_summary": "前一轮已经筛出了框架课视频。",
                "history_selected_videos": [
                    {"video_id": "1-6", "reason_for_selection": "框架课"},
                    {"video_id": "1-7", "reason_for_selection": "框架课"},
                ],
            }
        )

        self.assertIsNotNone(classifier.kwargs)
        self.assertEqual(classifier.kwargs["history_summary"], "前一轮已经筛出了框架课视频。")
        self.assertEqual(len(classifier.kwargs["history_selected_videos"]), 2)

    def test_series_content_flow_uses_planner_after_classifier_labels_content(self) -> None:
        class _ContentClassifier:
            def run(self, **kwargs):
                del kwargs
                return StructuredQueryPlan(
                    goal="understand",
                    target_source="summary",
                    context_need="chunk",
                    reason="classifier",
                )

        classifier = _ContentClassifier()
        planner = _CapturingSeriesPlanner(
            {
                "goal": "series_content",
                "target_source": "all",
                "context_need": "chunk",
                "reason": "planner",
                "candidate_video_ids": ["1-4", "1-5"],
                "selected_videos": [
                    {"video_id": "1-4", "reason_for_selection": "AK 准备"},
                    {"video_id": "1-5", "reason_for_selection": "Nacos 安装"},
                ],
                "selection_mode": "fresh",
                "subplans": [
                    {
                        "target_video_ids": ["1-4", "1-5"],
                        "depth": "summary",
                        "query": "按顺序说明这两节准备了什么",
                    }
                ],
            }
        )

        graph = build_agent_graph(
            classifier_program=classifier,
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            pinpoint_service=_PinpointService(),
            answer_program=_Answer(),
            series_planner=planner,
        )

        result = graph.invoke(
            {
                "session_id": "series|series-a|home",
                "scope_type": "series",
                "series_id": "series-a",
                "user_message": "把准备工作的视频找出来，并按顺序说每节在准备什么",
            }
        )

        self.assertIsNotNone(planner.kwargs)
        self.assertEqual(planner.kwargs["series_id"], "series-a")
        self.assertEqual(result["query_plan"]["candidate_video_ids"], ["1-4", "1-5"])
        self.assertEqual(result["query_plan"]["selected_videos"][1]["video_id"], "1-5")
        self.assertEqual(result["query_plan"]["subplans"][0]["target_video_ids"], ["1-4", "1-5"])

    def test_series_action_flow_uses_classifier_directly(self) -> None:
        class _ContentClassifier:
            def run(self, **kwargs):
                del kwargs
                return StructuredQueryPlan(
                    goal="action",
                    target_source="all",
                    context_need="chunk",
                    reason="动作请求",
                    action_name="open_notes",
                )

        planner = _CapturingSeriesPlanner(
            {"goal": "series_content", "target_source": "all", "context_need": "chunk", "subplans": []}
        )

        graph = build_agent_graph(
            classifier_program=_ContentClassifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            pinpoint_service=_PinpointService(),
            action_dispatcher=_ActionDispatcher(),
            answer_program=_Answer(),
            series_planner=planner,
        )

        result = graph.invoke(
            {
                "session_id": "series|series-a|home",
                "scope_type": "series",
                "series_id": "series-a",
                "user_message": "打开笔记",
            }
        )

        self.assertIsNone(planner.kwargs)
        self.assertEqual(result["assistant_message"], "已打开笔记")
        self.assertEqual(result["tool_results"][0]["tool_name"], "open_notes")

    def test_series_meta_state_flow_uses_classifier_directly(self) -> None:
        class _Classifier:
            def run(self, **kwargs):
                del kwargs
                return StructuredQueryPlan(
                    goal="meta_state",
                    target_source="all",
                    context_need="chunk",
                    reason="状态请求",
                )

        class _MetaStateReader:
            def read(self, **kwargs):
                del kwargs
                return {"video_count": 7}

        class _MetaAnswer:
            def run(self, *, user_message: str, retrieval_results: list[dict[str, object]], meta_state=None):
                del user_message, retrieval_results
                return f"视频数 {meta_state['video_count']}"

        planner = _CapturingSeriesPlanner(
            {"goal": "series_content", "target_source": "all", "context_need": "chunk", "subplans": []}
        )

        graph = build_agent_graph(
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            pinpoint_service=_PinpointService(),
            meta_state_reader=_MetaStateReader(),
            answer_program=_MetaAnswer(),
            series_planner=planner,
        )

        result = graph.invoke(
            {
                "session_id": "series|series-a|home",
                "scope_type": "series",
                "series_id": "series-a",
                "user_message": "这个系列一共有多少视频？",
            }
        )

        self.assertIsNone(planner.kwargs)
        self.assertEqual(result["meta_state"]["video_count"], 7)
        self.assertEqual(result["answer"], "视频数 7")

    def test_series_content_flow_uses_series_aggregator_instead_of_generic_answer_program(self) -> None:
        class _Classifier:
            def run(self, **kwargs):
                del kwargs
                return StructuredQueryPlan(
                    goal="understand",
                    target_source="all",
                    context_need="chunk",
                    reason="classifier",
                    candidate_video_ids=["1-5"],
                    selected_videos=[
                        {"video_id": "1-5", "reason_for_selection": "Nacos 安装"},
                    ],
                    selection_mode="fresh",
                    subplans=[
                        {
                            "target_video_ids": ["1-5"],
                            "depth": "video_graph",
                            "query": "定位安装、端口、登录信息",
                        }
                    ],
                )

        graph = build_agent_graph(
            classifier_program=_Classifier(),
            compare_split_program=_Splitter(),
            retrieval_service=_Retrieval(),
            pinpoint_service=_PinpointService(),
            answer_program=_ExplodingAnswer(),
            series_aggregator=_SeriesAggregator(),
        )

        result = graph.invoke(
            {
                "session_id": "series|series-a|home",
                "scope_type": "series",
                "series_id": "series-a",
                "user_message": "在这个系列里，哪一节讲 Nacos 安装、端口和登录信息？",
            }
        )

        self.assertEqual(result["answer"], "聚合:selected=1-5;results=1;first_depth=video_graph")


if __name__ == "__main__":
    unittest.main()
