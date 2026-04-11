from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy_opt import DspyCompiler, DspyEvaluator


class _Optimizer:
    def __init__(self) -> None:
        self.called_with = None

    def compile(self, *, student, trainset, valset=None):
        self.called_with = (student, trainset, valset)
        return {"compiled": True, "student": student}


class _Evaluate:
    def __init__(self, *, devset, metric, num_threads=None, display_progress=False, display_table=False):
        self.devset = devset
        self.metric = metric
        self.num_threads = num_threads
        self.display_progress = display_progress
        self.display_table = display_table

    def __call__(self, program):
        return {"score": 1.0, "program": program}


class AgentGraphDspyOptTests(unittest.TestCase):
    def test_compiler_wraps_optimizer_compile(self) -> None:
        optimizer = _Optimizer()
        compiler = DspyCompiler(optimizer=optimizer)

        result = compiler.compile_program(
            student={"name": "classifier"},
            trainset=[{"x": 1}],
            valset=[{"x": 2}],
        )

        self.assertTrue(result["compiled"])
        self.assertEqual(optimizer.called_with[1], [{"x": 1}])

    def test_evaluator_wraps_dspy_evaluate(self) -> None:
        evaluator = DspyEvaluator(evaluate_factory=_Evaluate)

        result = evaluator.evaluate_program(
            program={"name": "classifier"},
            devset=[{"x": 1}],
            metric=lambda example, prediction: 1.0,
        )

        self.assertEqual(result["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
