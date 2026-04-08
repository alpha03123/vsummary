from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.memory.context import AgentContext, CandidateBufferEntry, InspectionStage
from backend.agent.runtime.model_visible_context import render_model_visible_context_json
from backend.agent.runtime.request_router import REQUEST_ROUTER_SYSTEM_PROMPT


class AgentPromptContractTests(unittest.TestCase):
    def test_request_router_prompt_no_longer_mentions_planner_fallback(self) -> None:
        self.assertNotIn("planner", REQUEST_ROUTER_SYSTEM_PROMPT.lower())
        self.assertNotIn("fallback", REQUEST_ROUTER_SYSTEM_PROMPT.lower())

    def test_model_visible_context_json_hides_runtime_internal_state(self) -> None:
        rendered = render_model_visible_context_json(
            AgentContext(
                session_id="series|agent-frameworks|series-home",
                scope_type="series",
                series_id="agent-frameworks",
                inspection_stage=InspectionStage.VIDEO_INSPECTION,
                candidate_buffer=[CandidateBufferEntry(video_id="video-1", title="Video 1")],
                inspected_video_ids=["video-1"],
                rejected_video_ids=["video-2"],
            )
        )

        self.assertNotIn("candidate_buffer", rendered)
        self.assertNotIn("inspected_video_ids", rendered)
        self.assertNotIn("rejected_video_ids", rendered)
        self.assertNotIn("inspection_stage", rendered)

if __name__ == "__main__":
    unittest.main()
