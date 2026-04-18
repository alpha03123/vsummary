from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy_compile import SeriesQueryClassifierModule


class AgentGraphDspyCompileTests(unittest.TestCase):
    def test_classifier_module_run_accepts_history_context(self) -> None:
        module = SeriesQueryClassifierModule()
        captured = {}

        def fake_predict(**kwargs):
            captured.update(kwargs)
            return {
                "goal": "understand",
                "target_source": "summary",
                "context_need": "chunk",
                "reason": "ok",
            }

        module.predict = fake_predict
        result = module.run(
            user_message="继续比较它们的定位差异",
            scope_type="series",
            series_id="agent-frameworks",
            history_summary="上一轮已经筛出了框架课视频。",
            history_selected_videos=[
                {"video_id": "1-6", "reason_for_selection": "框架课"},
                {"video_id": "1-7", "reason_for_selection": "框架课"},
            ],
        )

        self.assertEqual(result.goal, "understand")
        self.assertEqual(captured["history_summary"], "上一轮已经筛出了框架课视频。")
        self.assertEqual(len(captured["history_selected_videos"]), 2)


if __name__ == "__main__":
    unittest.main()
