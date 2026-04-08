from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.runtime.evidence_policy import build_followup_plan
from backend.agent.schemas.action_plan import AgentActionPlan, IntentType, ScopeType
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class AgentEvidencePolicyTests(unittest.TestCase):
    def test_series_answer_after_listing_defaults_to_batch_summary_reads(self) -> None:
        plan = build_followup_plan(
            context=AgentContext(
                session_id="series|agent-frameworks|series-home",
                scope_type="series",
                series_id="agent-frameworks",
                inspection_stage=InspectionStage.VIDEO_INSPECTION,
            ),
            observed_tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.LIST_SERIES_VIDEOS,
                    status="ok",
                    payload={
                        "videos": [
                            {"video_id": "video-1", "title": "Video 1"},
                            {"video_id": "video-2", "title": "Video 2"},
                        ]
                    },
                )
            ],
            last_tool_plan=AgentActionPlan(
                intent_type=IntentType.SERIES_ANSWER,
                scope_type=ScopeType.SERIES,
                tool_calls=[],
                reason="先列出系列视频",
            ),
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual([call.video_id for call in plan.tool_calls], ["video-1", "video-2"])
        self.assertTrue(all(call.tool_name == ToolName.GET_VIDEO_SUMMARY for call in plan.tool_calls))

    def test_series_answer_does_not_repeat_when_series_reads_already_exist(self) -> None:
        plan = build_followup_plan(
            context=AgentContext(
                session_id="series|agent-frameworks|series-home",
                scope_type="series",
                series_id="agent-frameworks",
                inspection_stage=InspectionStage.VIDEO_INSPECTION,
            ),
            observed_tool_results=[
                ToolExecutionResult(
                    tool_name=ToolName.LIST_SERIES_VIDEOS,
                    status="ok",
                    payload={"videos": [{"video_id": "video-1", "title": "Video 1"}]},
                ),
                ToolExecutionResult(
                    tool_name=ToolName.GET_VIDEO_SUMMARY,
                    status="ok",
                    payload={"video_id": "video-1"},
                ),
            ],
            last_tool_plan=AgentActionPlan(
                intent_type=IntentType.SERIES_ANSWER,
                scope_type=ScopeType.SERIES,
                tool_calls=[],
                reason="先列出系列视频",
            ),
        )

        self.assertIsNone(plan)

    def test_non_series_answer_returns_none(self) -> None:
        plan = build_followup_plan(
            context=AgentContext(
                session_id="video|agent-frameworks|video-1|overview",
                scope_type="video",
                series_id="agent-frameworks",
                video_id="video-1",
            ),
            observed_tool_results=[],
            last_tool_plan=AgentActionPlan(
                intent_type=IntentType.ANSWER_QUESTION,
                scope_type=ScopeType.VIDEO,
                tool_calls=[],
                reason="直接回答",
            ),
        )

        self.assertIsNone(plan)


if __name__ == "__main__":
    unittest.main()
