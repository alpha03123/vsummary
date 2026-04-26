from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy.program_loader import (
    load_or_create_classifier_program,
    load_or_create_split_compare_program,
)


class _FakeProgram:
    def __init__(self) -> None:
        self.loaded_path = None

    def load_state(self, state):
        self.loaded_path = state
        return self


class AgentGraphProgramLoaderTests(unittest.TestCase):
    def test_load_or_create_classifier_program_loads_existing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "program.json"
            artifact.write_text('{"predict": {}, "metadata": {}}', encoding="utf-8")
            program = _FakeProgram()

            result = load_or_create_classifier_program(
                artifact_path=artifact,
                program_factory=lambda: program,
            )

            self.assertIs(result, program)
            self.assertEqual(program.loaded_path["metadata"], {})

    def test_load_or_create_split_compare_program_loads_existing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "program.json"
            artifact.write_text('{"predict": {}, "metadata": {}}', encoding="utf-8")
            program = _FakeProgram()

            result = load_or_create_split_compare_program(
                artifact_path=artifact,
                program_factory=lambda: program,
            )

            self.assertIs(result, program)
            self.assertEqual(program.loaded_path["metadata"], {})


if __name__ == "__main__":
    unittest.main()
