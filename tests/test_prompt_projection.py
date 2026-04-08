from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext
from backend.agent.runtime.prompt_projection import build_prompt_projection
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class PromptProjectionTests(unittest.TestCase):
    def test_transcript_projection_only_keeps_relevant_segments(self) -> None:
        projection = build_prompt_projection(
            context=AgentContext(
                session_id="series|series-a|series-home",
                scope_type="series",
                series_id="series-a",
            ),
            user_message="这个系列里哪里讲过 Nacos 3？",
            plan=AgentActionPlan.model_validate(
                {
                    "intent_type": "series_locate",
                    "scope_type": "series",
                    "tool_calls": [],
                    "reason": "定位 Nacos 3",
                }
            ),
            tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                    status="ok",
                    payload={
                        "series_id": "series-a",
                        "video_id": "video-1",
                        "title": "安装 Nacos 3",
                        "duration_seconds": 300,
                        "segments": [
                            {"start_seconds": 10, "end_seconds": 20, "text": "这一段在讲百度地图 API Key。"},
                            {"start_seconds": 30, "end_seconds": 40, "text": "这里明确提到 Nacos 3 的安装方式。"},
                            {"start_seconds": 50, "end_seconds": 60, "text": "这里继续解释为什么课程使用 Nacos 3。"},
                            {"start_seconds": 70, "end_seconds": 80, "text": "这一段在讲其他内容。"},
                        ],
                    },
                )
            ],
        )

        transcript_projection = projection["evidence"][0]["payload"]["segments"]
        self.assertEqual(len(transcript_projection), 2)
        self.assertIn("Nacos 3", transcript_projection[0]["text"])
        self.assertIn("Nacos 3", transcript_projection[1]["text"])

    def test_summary_projection_trims_takeaways_and_chapters(self) -> None:
        projection = build_prompt_projection(
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="这个视频主要讲了什么？",
            plan=AgentActionPlan.model_validate(
                {
                    "intent_type": "answer_question",
                    "scope_type": "video",
                    "tool_calls": [],
                    "reason": "概括视频",
                }
            ),
            tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_SUMMARY,
                    status="ok",
                    payload={
                        "series_id": "series-a",
                        "video_id": "video-1",
                        "title": "Video 1",
                        "generated": True,
                        "one_sentence_summary": "一句话总结",
                        "core_problem": "核心问题",
                        "key_takeaways": ["1", "2", "3", "4", "5", "6", "7"],
                        "chapters": [
                            {"title": "A", "summary": "a"},
                            {"title": "B", "summary": "b"},
                            {"title": "C", "summary": "c"},
                            {"title": "D", "summary": "d"},
                            {"title": "E", "summary": "e"},
                        ],
                    },
                )
            ],
        )

        summary_payload = projection["evidence"][0]["payload"]
        self.assertEqual(len(summary_payload["key_takeaways"]), 5)
        self.assertEqual(len(summary_payload["chapters"]), 4)

    def test_projection_shrinks_when_budget_is_tight(self) -> None:
        projection = build_prompt_projection(
            context=AgentContext(
                session_id="video|series-a|video-1|overview",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            user_message="这个视频原话里 Nacos 3 是怎么说的？",
            plan=AgentActionPlan.model_validate(
                {
                    "intent_type": "answer_question",
                    "scope_type": "video",
                    "tool_calls": [],
                    "reason": "需要转写证据",
                }
            ),
            tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_SUMMARY,
                    status="ok",
                    payload={
                        "series_id": "series-a",
                        "video_id": "video-1",
                        "title": "Video 1",
                        "generated": True,
                        "one_sentence_summary": "一句话总结",
                        "core_problem": "核心问题",
                        "key_takeaways": ["1", "2", "3", "4", "5", "6", "7"],
                        "chapters": [{"title": str(i), "summary": "x" * 50} for i in range(8)],
                    },
                ),
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_TRANSCRIPT,
                    status="ok",
                    payload={
                        "series_id": "series-a",
                        "video_id": "video-1",
                        "title": "Video 1",
                        "duration_seconds": 300,
                        "segments": [
                            {"start_seconds": i * 10, "end_seconds": i * 10 + 5, "text": f"Nacos 3 相关说明 {i} " + "x" * 120}
                            for i in range(10)
                        ],
                    },
                ),
            ],
            max_tokens=120,
        )

        summary_payload = projection["evidence"][0]["payload"]
        transcript_payload = projection["evidence"][1]["payload"]
        self.assertEqual(summary_payload["chapters"], [])
        self.assertLessEqual(len(summary_payload["key_takeaways"]), 3)
        self.assertLessEqual(len(transcript_payload["segments"]), 2)


if __name__ == "__main__":
    unittest.main()
