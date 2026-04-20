from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy.split_compare_compile import SplitCompareMetric, SplitCompareModule, compile_split_compare_program


class _Optimizer:
    def __init__(self) -> None:
        self.student = None
        self.trainset = None

    def compile(self, student, *, teacher=None, trainset):
        del teacher
        self.student = student
        self.trainset = trainset
        return {"compiled": True, "student": student}


class AgentGraphSplitCompareCompileTests(unittest.TestCase):
    def test_split_compare_metric_scores_exact_match(self) -> None:
        metric = SplitCompareMetric()
        score = metric(
            example={"queries": ["Jmanus", "AgentScope"]},
            prediction={"queries": ["Jmanus", "AgentScope"]},
        )

        self.assertEqual(score, 1.0)

    def test_compile_split_compare_program_uses_module_and_optimizer(self) -> None:
        optimizer = _Optimizer()
        result = compile_split_compare_program(trainset=[{"id": "cseed-001"}], optimizer=optimizer)

        self.assertTrue(result["compiled"])
        self.assertIsInstance(optimizer.student, SplitCompareModule)

    def test_split_compare_module_exposes_run_interface(self) -> None:
        module = SplitCompareModule()
        module.predict = lambda **_: {
            "queries": ["百度地图 API Key", "Nacos 3"],
            "reason": "需要分别检索。",
        }

        result = module.run(
            user_message="百度地图 API Key 和 Nacos 3 在课程里分别承担什么作用？",
        )

        self.assertEqual(result.queries, ["百度地图 API Key", "Nacos 3"])


if __name__ == "__main__":
    unittest.main()
