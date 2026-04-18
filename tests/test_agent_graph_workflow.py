from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.graph import build_series_agent_graph
from backend.agent_graph.models import DecomposeDecision
from backend.agent_graph.video_workflow import VideoWorkflowExtractor
from backend.video_summary.library.views import TranscriptSegmentView, VideoTranscriptView


class _Decomposer:
    def run(self, *, user_message: str, scope_type: str, series_id: str, video_id: str = ""):
        del scope_type, series_id, video_id
        return DecomposeDecision(
            tasks=[{"task_id": "task-1", "instruction": user_message, "depends_on": [], "kind_hint": ""}],
            reason="单任务。",
        )


class _SeriesPlanner:
    def create_plan(self, **kwargs):
        del kwargs
        return {
            "goal": "series_content",
            "target_source": "all",
            "context_need": "continuous",
            "reason": "workflow",
            "candidate_video_ids": ["1-6"],
            "selected_videos": [{"video_id": "1-6", "reason_for_selection": "JManus 演示流程"}],
            "selection_mode": "fresh",
            "subplans": [
                {
                    "target_video_ids": ["1-6"],
                    "depth": "video_workflow",
                    "query": "JManus 那节里，老师演示的完整任务到底是什么？系统创建了哪几个 Agent，各自负责什么，最后文件被保存到了哪里？请尽量按视频里的执行顺序说。",
                    "needs_probe": True,
                }
            ],
        }


class _ExplodingClassifier:
    def run(self, **kwargs):
        raise AssertionError(f"classifier should not run for workflow series path: {kwargs}")


class _Splitter:
    def run(self, *, user_message: str):
        del user_message
        raise AssertionError("compare split should not run for workflow path")


class _ExplodingPinpoint:
    def locate(self, **kwargs):
        raise AssertionError(f"workflow path should not call pinpoint: {kwargs}")


class _WorkflowService:
    def extract(self, *, series_id: str, video_id: str, query: str):
        del series_id, query
        return (
            {
                "video_id": video_id,
                "title": "JManus",
                "query": "workflow",
                "source_type": "workflow_window",
                "windows": [
                    {
                        "start_seconds": 860.0,
                        "end_seconds": 1248.0,
                        "text": (
                            "通过百度去查询阿里巴巴的最新股价，并且将结果保存到本地的TXT后缀名的文件。 "
                            "Browser Agent 负责浏览器操作和查询。 "
                            "Default Agent 负责后续整理与写入。 "
                            "Extensions Inner_Storage Plan 目录里保存了结果。"
                        ),
                    }
                ],
                "best_window": {
                    "start_seconds": 860.0,
                    "end_seconds": 1248.0,
                    "text": (
                        "通过百度去查询阿里巴巴的最新股价，并且将结果保存到本地的TXT后缀名的文件。 "
                        "Browser Agent 负责浏览器操作和查询。 "
                        "Default Agent 负责后续整理与写入。 "
                        "Extensions Inner_Storage Plan 目录里保存了结果。"
                    ),
                },
                "transcript_missing": False,
            },
            [
                {"tool_name": "get_video_transcript", "status": "ok", "payload": {"video_id": video_id, "title": "JManus", "match_count": 4}},
                {"tool_name": "video_seek", "status": "ok", "payload": {"video_id": video_id, "seek_seconds": 860.0}},
            ],
        )


class _SeriesAggregator:
    def run(self, *, user_message: str, query_plan: dict[str, object], execution_results: list[dict[str, object]], tool_results: list[dict[str, object]], history_messages=None, debug_trace=None):
        del user_message, tool_results, history_messages, debug_trace
        return f"{query_plan['subplans'][0]['depth']}|{execution_results[0]['items'][0]['source_type']}"


class _ExplodingAnswer:
    def run(self, **kwargs):
        raise AssertionError(f"workflow path should not use generic answer program: {kwargs}")


class _MemoryUpdater:
    def run(self, *, history_summary: str, user_message: str, assistant_message: str, task_outputs: list[dict[str, object]]):
        del history_summary, user_message, assistant_message, task_outputs
        return ""


class _Workspace:
    def get_video_transcript(self, series_id: str, video_id: str):
        del series_id, video_id
        return VideoTranscriptView(
            series_id="agent-frameworks",
            video_id="1-6",
            title="JManus",
            duration_seconds=None,
            segments=[
                TranscriptSegmentView(start_seconds=869.0, end_seconds=874.0, text="就是通过百度去查询阿里巴巴的最新股价"),
                TranscriptSegmentView(start_seconds=874.0, end_seconds=879.0, text="并且将结果保存到本地的TXT后缀名的文件"),
                TranscriptSegmentView(start_seconds=954.0, end_seconds=959.0, text="看一下它创建了哪几个Agent来完成我们这个需求"),
                TranscriptSegmentView(start_seconds=974.0, end_seconds=979.0, text="就是Browser Agent"),
                TranscriptSegmentView(start_seconds=1014.0, end_seconds=1019.0, text="这个Agent的名称叫做Default Agent"),
                TranscriptSegmentView(start_seconds=1119.0, end_seconds=1124.0, text="这里在这个JManus项目里面的这个Extensions"),
                TranscriptSegmentView(start_seconds=1144.0, end_seconds=1149.0, text="Inner_Storage这个文件夹"),
                TranscriptSegmentView(start_seconds=1159.0, end_seconds=1164.0, text="对，就是这里，Plan这个"),
                TranscriptSegmentView(start_seconds=1204.0, end_seconds=1209.0, text="它创建了两个Agent来去完成这个需求"),
                TranscriptSegmentView(start_seconds=1209.0, end_seconds=1214.0, text="第一个Agent主要就是进行浏览器的操作"),
                TranscriptSegmentView(start_seconds=1224.0, end_seconds=1229.0, text="而第二个Agent"),
                TranscriptSegmentView(start_seconds=1244.0, end_seconds=1249.0, text="然后把这些信息保存到TXT的文件里面"),
            ],
        )


class AgentGraphWorkflowTests(unittest.TestCase):
    def test_series_workflow_subplan_routes_to_workflow_executor(self) -> None:
        graph = build_series_agent_graph(
            decomposer_program=_Decomposer(),
            classifier_program=_ExplodingClassifier(),
            compare_split_program=_Splitter(),
            series_planner=_SeriesPlanner(),
            pinpoint_service=_ExplodingPinpoint(),
            workflow_service=_WorkflowService(),
            series_aggregator=_SeriesAggregator(),
            answer_program=_ExplodingAnswer(),
            memory_update_program=_MemoryUpdater(),
        )

        result = graph.invoke(
            {
                "session_id": "series|agent-frameworks|series-home|lt-04",
                "scope_type": "series",
                "series_id": "agent-frameworks",
                "user_message": "JManus 那节里，老师演示的完整任务到底是什么？系统创建了哪几个 Agent，各自负责什么，最后文件被保存到了哪里？请尽量按视频里的执行顺序说。",
            }
        )

        self.assertEqual(result["retrieval_results"][0]["depth"], "video_workflow")
        self.assertEqual(result["retrieval_results"][0]["items"][0]["source_type"], "workflow_window")
        self.assertEqual(result["answer"], "video_workflow|workflow_window")

    def test_workflow_extractor_returns_continuous_window_covering_task_agents_and_path(self) -> None:
        extractor = VideoWorkflowExtractor(workspace=_Workspace(), semantic_scorer=None)

        result, tool_results = extractor.extract(
            series_id="agent-frameworks",
            video_id="1-6",
            query="JManus 那节里，老师演示的完整任务到底是什么？系统创建了哪几个 Agent，各自负责什么，最后文件被保存到了哪里？请尽量按视频里的执行顺序说。",
        )

        self.assertEqual(result["source_type"], "workflow_window")
        self.assertLessEqual(result["best_window"]["start_seconds"], 869.0)
        self.assertIn("阿里巴巴的最新股价", result["best_window"]["text"])
        self.assertIn("Browser Agent", result["best_window"]["text"])
        self.assertIn("Default Agent", result["best_window"]["text"])
        self.assertIn("Extensions", result["best_window"]["text"])
        self.assertIn("Inner_Storage", result["best_window"]["text"])
        self.assertIn("Plan", result["best_window"]["text"])
        self.assertEqual(tool_results[0]["tool_name"], "get_video_transcript")


if __name__ == "__main__":
    unittest.main()
