from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.plan import validate_action_plan


class AgentValidationTests(unittest.TestCase):
    def test_answer_question_rejects_tool_calls(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "intent_type": "answer_question",
                "scope_type": "video",
                "tool_calls": [{"tool_name": "transcript_lookup", "query": "测试"}],
                "reason": "直接回答即可",
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan)

    def test_open_tool_requires_open_tool_call(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "intent_type": "open_tool",
                "scope_type": "video",
                "tool_calls": [{"tool_name": "generate_overview"}],
                "reason": "用户要切到工具页",
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan)

    def test_seek_video_rejects_library_scope(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "intent_type": "seek_video",
                "scope_type": "library",
                "tool_calls": [{"tool_name": "video_seek", "seek_seconds": 12}],
                "reason": "需要跳转视频",
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan)

    def test_generate_mindmap_requires_matching_tool(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "intent_type": "generate_mindmap",
                "scope_type": "video",
                "tool_calls": [{"tool_name": "generate_overview"}],
                "reason": "用户要生成导图",
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan)

    def test_out_of_scope_requires_reason(self) -> None:
        plan = AgentActionPlan.model_validate(
            {
                "intent_type": "out_of_scope",
                "scope_type": "series",
                "tool_calls": [],
                "reason": "与工作台无关",
                "out_of_scope_reason": "",
            }
        )

        with self.assertRaises(AgentPlanError):
            validate_action_plan(plan)


if __name__ == "__main__":
    unittest.main()
