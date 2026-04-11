from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.programs import (
    AnswerSynthesisProgram,
    CompareSplitProgram,
    SeriesQueryClassifierProgram,
)


class AgentGraphProgramsTests(unittest.TestCase):
    def test_series_query_classifier_program_returns_structured_fields(self) -> None:
        program = SeriesQueryClassifierProgram(
            predictor=lambda **_: {
                "goal": "locate",
                "target_source": "transcript",
                "context_need": "chunk",
                "reason": "需要定位命中位置。",
            }
        )

        result = program.run(
            user_message="这个系列里哪里讲过 Nacos 3？",
            scope_type="series",
            series_id="agent-frameworks",
        )

        self.assertEqual(result.goal, "locate")
        self.assertEqual(result.target_source, "transcript")
        self.assertEqual(result.context_need, "chunk")

    def test_compare_split_program_returns_atomic_queries(self) -> None:
        program = CompareSplitProgram(
            predictor=lambda **_: {
                "queries": ["百度地图 API Key", "Nacos 3"],
                "reason": "需要分开检索。",
            }
        )

        result = program.run(
            user_message="百度地图 API Key 和 Nacos 3 在课程里分别承担什么作用？",
        )

        self.assertEqual(result.queries, ["百度地图 API Key", "Nacos 3"])

    def test_answer_synthesis_program_returns_answer_text(self) -> None:
        program = AnswerSynthesisProgram(
            predictor=lambda **_: {
                "answer": "Nacos 3 主要出现在 1-5，重点讲安装和课程中的定位。"
            }
        )

        answer = program.run(
            user_message="这个系列里哪里讲过 Nacos 3？",
            retrieval_results=[{"video_id": "1-5", "snippet": "这里讲 Nacos 3。"}],
        )

        self.assertIn("Nacos 3", answer)

    def test_answer_synthesis_program_accepts_meta_state_argument(self) -> None:
        captured = {}

        def predictor(**kwargs):
            captured.update(kwargs)
            return {"answer": "资源状态已整理。"}

        program = AnswerSynthesisProgram(predictor=predictor)

        answer = program.run(
            user_message="这个视频有哪些工具已经生成了？",
            retrieval_results=[],
            meta_state={"overview": {"status": "ready"}},
        )

        self.assertEqual(answer, "资源状态已整理。")
        self.assertEqual(captured["meta_state"]["overview"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
