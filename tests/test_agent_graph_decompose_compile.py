from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy.decompose_compile import DecomposeMetric, TaskDecomposerModule, compile_decompose_program


class _Optimizer:
    def __init__(self) -> None:
        self.student = None
        self.trainset = None

    def compile(self, student, *, teacher=None, trainset):
        del teacher
        self.student = student
        self.trainset = trainset
        return {"compiled": True, "student": student}


class AgentGraphDecomposeCompileTests(unittest.TestCase):
    def test_decompose_metric_scores_exact_match(self) -> None:
        metric = DecomposeMetric()
        score = metric(
            example={
                "tasks": [
                    {"instruction": "概括当前视频主要内容", "depends_on": [], "kind_hint": "understand"}
                ]
            },
            prediction={
                "tasks": [
                    {"instruction": "概括当前视频主要内容", "depends_on": [], "kind_hint": "understand"}
                ]
            },
        )

        self.assertEqual(score, 1.0)

    def test_compile_decompose_program_uses_module_and_optimizer(self) -> None:
        optimizer = _Optimizer()
        result = compile_decompose_program(trainset=[{"id": "dseed-001"}], optimizer=optimizer)

        self.assertTrue(result["compiled"])
        self.assertIsInstance(optimizer.student, TaskDecomposerModule)

    def test_task_decomposer_module_exposes_run_interface(self) -> None:
        module = TaskDecomposerModule()
        module.predict = lambda **_: {
            "tasks": [
                {"task_id": "task-1", "instruction": "概括当前视频主要内容", "depends_on": [], "kind_hint": "understand"}
            ],
            "reason": "单任务。",
        }

        result = module.run(
            user_message="这个视频主要讲了什么？",
            scope_type="video",
            series_id="series-a",
            video_id="video-1",
        )

        self.assertEqual(result.tasks[0].instruction, "概括当前视频主要内容")


if __name__ == "__main__":
    unittest.main()
