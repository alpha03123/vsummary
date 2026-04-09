from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext, InspectionStage
from backend.agent.runtime.model_visible_context import render_model_visible_context_json
from backend.agent.runtime.planner import INITIAL_PLANNER_SYSTEM_PROMPT


class AgentPromptContractTests(unittest.TestCase):
    def test_initial_planner_prompt_describes_direct_plan_instead_of_route_labels(self) -> None:
        self.assertNotIn("路由", INITIAL_PLANNER_SYSTEM_PROMPT)
        self.assertNotIn("分类", INITIAL_PLANNER_SYSTEM_PROMPT)
        self.assertIn("直接决定下一步", INITIAL_PLANNER_SYSTEM_PROMPT)

    def test_model_visible_context_json_hides_runtime_internal_state(self) -> None:
        rendered = render_model_visible_context_json(
            AgentContext(
                session_id="series|agent-frameworks|series-home",
                scope_type="series",
                series_id="agent-frameworks",
                inspection_stage=InspectionStage.VIDEO_INSPECTION,
            )
        )

        self.assertNotIn("inspection_stage", rendered)

if __name__ == "__main__":
    unittest.main()
