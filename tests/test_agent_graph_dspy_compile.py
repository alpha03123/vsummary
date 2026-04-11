from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy_compile import (
    ClassifierMetric,
    SeriesQueryClassifierModule,
    compile_classifier_program,
    evaluate_classifier_program,
)


class _Optimizer:
    def __init__(self) -> None:
        self.student = None
        self.trainset = None

    def compile(self, student, *, teacher=None, trainset):
        del teacher
        self.student = student
        self.trainset = trainset
        return {"compiled": True, "student": student}


class _Evaluate:
    def __init__(self, *, devset, metric, num_threads=None, display_progress=False, display_table=False):
        self.devset = devset
        self.metric = metric
        self.num_threads = num_threads
        self.display_progress = display_progress
        self.display_table = display_table

    def __call__(self, program):
        return {"score": 0.88, "program": program}


class AgentGraphDspyCompileTests(unittest.TestCase):
    def test_classifier_metric_scores_exact_match(self) -> None:
        metric = ClassifierMetric()
        score = metric(
            example={
                "goal": "locate",
                "target_source": "transcript",
                "context_need": "chunk",
                "action_name": "",
                "action_args": {},
            },
            prediction={
                "goal": "locate",
                "target_source": "transcript",
                "context_need": "chunk",
                "action_name": "",
                "action_args": {},
            },
        )

        self.assertEqual(score, 1.0)

    def test_compile_classifier_program_uses_dspy_module_and_optimizer(self) -> None:
        optimizer = _Optimizer()
        trainset = [{"id": "seed-001"}]

        result = compile_classifier_program(
            trainset=trainset,
            optimizer=optimizer,
        )

        self.assertTrue(result["compiled"])
        self.assertIsInstance(optimizer.student, SeriesQueryClassifierModule)
        self.assertEqual(optimizer.trainset, trainset)

    def test_evaluate_classifier_program_uses_dspy_evaluate(self) -> None:
        result = evaluate_classifier_program(
            program={"name": "compiled"},
            devset=[{"id": "seed-003"}],
            evaluate_factory=_Evaluate,
            num_threads=4,
        )

        self.assertEqual(result["score"], 0.88)

    def test_classifier_module_exposes_run_interface(self) -> None:
        module = SeriesQueryClassifierModule()
        module.predict = lambda **_: {
            "goal": "locate",
            "target_source": "transcript",
            "context_need": "chunk",
            "reason": "定位问题。",
            "action_name": "",
            "action_args": {},
        }

        result = module.run(
            user_message="这个系列里哪里讲过 Nacos 3？",
            scope_type="series",
            series_id="agent-frameworks",
        )

        self.assertEqual(result.goal, "locate")


if __name__ == "__main__":
    unittest.main()
