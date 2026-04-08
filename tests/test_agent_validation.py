from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext, CandidateBufferEntry, InspectionStage
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.plan import validate_action_plan


def make_series_context(
    *,
    stage: InspectionStage = InspectionStage.SERIES_DISCOVERY,
    candidate_ids: list[str] | None = None,
) -> AgentContext:
    candidate_buffer = [
        CandidateBufferEntry(video_id=video_id, title=video_id, processed=True, status="ready")
        for video_id in (candidate_ids or [])
    ]
    return AgentContext(
        session_id="series|agent-frameworks|series-home",
        scope_type="series",
        series_id="agent-frameworks",
        series_title="Agent Frameworks",
        inspection_stage=stage,
        candidate_buffer=candidate_buffer,
    )


class AgentValidationTests(unittest.TestCase):
    def test_answer_question_allows_video_transcript_in_video_scope(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "video",
                "tool_calls": [{"tool_name": "get_video_transcript", "video_id": "video-1"}],
                "reason": "需要原文证据",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        validated = validate_action_plan(
            plan,
            AgentContext(
                session_id="video|series-a|video-1|studio",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
        )

        self.assertEqual(validated.tool_calls[0].tool_name.value, "get_video_transcript")

    def test_series_discovery_rejects_deep_video_tools(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                "reason": "直接读取单视频概况",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan, make_series_context())

    def test_video_inspection_allows_summary_only_for_candidate_buffer(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                "reason": "核验候选视频内容",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        validated = validate_action_plan(
            plan,
            make_series_context(
                stage=InspectionStage.VIDEO_INSPECTION,
                candidate_ids=["video-1"],
            ),
        )

        self.assertEqual(validated.tool_calls[0].tool_name.value, "get_video_summary")

    def test_video_inspection_allows_batch_tagged_summary_calls_within_candidate_buffer(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [
                    {"tool_name": "get_video_summary", "video_id": "video-1"},
                    {"tool_name": "get_video_summary", "video_id": "video-2"},
                    {"tool_name": "get_video_summary", "video_id": "video-3"},
                    {"tool_name": "get_video_summary", "video_id": "video-4"},
                    {"tool_name": "get_video_summary", "video_id": "video-5"},
                    {"tool_name": "get_video_summary", "video_id": "video-6"},
                ],
                "reason": "批量读取所有候选视频的大纲后再回答。",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        validated = validate_action_plan(
            plan,
            make_series_context(
                stage=InspectionStage.VIDEO_INSPECTION,
                candidate_ids=["video-1", "video-2", "video-3", "video-4", "video-5", "video-6"],
            ),
        )

        self.assertEqual(len(validated.tool_calls), 6)
        self.assertTrue(all(call.tool_name.value == "get_video_summary" for call in validated.tool_calls))

    def test_video_inspection_rejects_summary_outside_candidate_buffer(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-2"}],
                "reason": "错误地读取缓冲区外视频",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(
                plan,
                make_series_context(
                    stage=InspectionStage.VIDEO_INSPECTION,
                    candidate_ids=["video-1"],
                ),
            )

    def test_video_inspection_allows_batch_tagged_transcript_calls_within_candidate_buffer(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [
                    {"tool_name": "get_video_transcript", "video_id": "video-1"},
                    {"tool_name": "get_video_transcript", "video_id": "video-2"},
                ],
                "reason": "批量对候选视频做转写核验。",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        validated = validate_action_plan(
            plan,
            make_series_context(
                stage=InspectionStage.VIDEO_INSPECTION,
                candidate_ids=["video-1", "video-2"],
            ),
        )

        self.assertEqual(len(validated.tool_calls), 2)
        self.assertTrue(all(call.tool_name.value == "get_video_transcript" for call in validated.tool_calls))

    def test_series_discovery_accepts_candidate_buffer_management_tools(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [
                    {"tool_name": "list_series_videos"},
                    {"tool_name": "add_series_candidates", "video_ids": ["video-1"], "reason": "先加入候选"},
                ],
                "reason": "先浏览列表，再收集候选",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        validated = validate_action_plan(plan, make_series_context())

        self.assertEqual([call.tool_name.value for call in validated.tool_calls], ["list_series_videos", "add_series_candidates"])

    def test_series_discovery_rejects_repeated_non_batch_tool_calls(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [
                    {"tool_name": "list_series_videos"},
                    {"tool_name": "list_series_videos"},
                ],
                "reason": "错误地重复读取同一列表工具。",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan, make_series_context())

    def test_series_discovery_rejects_placeholder_video_ids(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [
                    {"tool_name": "add_series_candidates", "video_ids": ["*pending_from_list_series_videos*"], "reason": "错误占位"}
                ],
                "reason": "不合法",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan, make_series_context())

    def test_observed_list_is_only_fallback_when_candidate_buffer_is_empty(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "series",
                "tool_calls": [{"tool_name": "get_video_summary", "video_id": "video-1"}],
                "reason": "用列表里的真实 ID 继续规划",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        validated = validate_action_plan(
            plan,
            make_series_context(stage=InspectionStage.VIDEO_INSPECTION),
            [
                ToolExecutionResult(
                    tool_name=ToolName.LIST_SERIES_VIDEOS,
                    status="ok",
                    payload={
                        "videos": [
                            {"video_id": "video-1", "title": "Video 1"},
                        ]
                    },
                )
            ],
        )

        self.assertEqual(validated.tool_calls[0].video_id, "video-1")

    def test_open_tool_rejects_empty_first_round(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "video",
                "tool_calls": [],
                "reason": "直接结束。",
                "direct_response": "",
                "use_answerer": False,
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(
                plan,
                AgentContext(
                    session_id="video|series-a|video-1|studio",
                    scope_type="video",
                    series_id="series-a",
                    video_id="video-1",
                ),
            )

    def test_open_tool_allows_empty_terminal_round_after_tool_result(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "scope_type": "video",
                "tool_calls": [],
                "reason": "工具已经执行完成，当前只需要回复。",
                "direct_response": "我已经帮你打开知识卡片。",
                "use_answerer": False,
            }
        )

        validated = validate_action_plan(
            plan,
            AgentContext(
                session_id="video|series-a|video-1|studio",
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
            ),
            [
                ToolExecutionResult(
                    tool_name=ToolName.OPEN_KNOWLEDGE_CARDS,
                    status="ok",
                    payload={"selected_tool": "knowledge-cards"},
                )
            ],
        )

        self.assertEqual(validated.direct_response, "我已经帮你打开知识卡片。")


if __name__ == "__main__":
    unittest.main()
