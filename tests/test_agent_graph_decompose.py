from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.models import DecomposeDecision
from backend.agent_graph.programs import TaskDecomposerProgram


class AgentGraphDecomposeTests(unittest.TestCase):
    def test_task_decomposer_program_returns_task_list(self) -> None:
        program = TaskDecomposerProgram(
            predictor=lambda **_: {
                "tasks": [
                    {"task_id": "task-1", "instruction": "总结重点", "depends_on": [], "kind_hint": "understand"},
                    {"task_id": "task-2", "instruction": "保存笔记", "depends_on": ["task-1"], "kind_hint": "action"},
                ],
                "reason": "这是一个复合任务。",
            }
        )

        result = program.run(
            user_message="先总结重点，再保存笔记",
            scope_type="video",
            series_id="series-a",
            video_id="video-1",
        )

        self.assertIsInstance(result, DecomposeDecision)
        self.assertEqual(len(result.tasks), 2)
        self.assertEqual(result.tasks[1].depends_on, ["task-1"])


if __name__ == "__main__":
    unittest.main()
