from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy.decompose_dataset import (
    build_decompose_devset,
    build_decompose_trainset,
    load_decompose_records,
)


class AgentGraphDecomposeDatasetTests(unittest.TestCase):
    def test_load_decompose_records_reads_seed_and_variant_markdown(self) -> None:
        records = load_decompose_records(ROOT / "docs" / "plan")

        self.assertGreaterEqual(len(records), 50)
        self.assertTrue(any(record["id"] == "dseed-001" for record in records))
        self.assertTrue(any(record["id"] == "dvar-040" for record in records))

    def test_build_decompose_trainset_returns_examples(self) -> None:
        trainset = build_decompose_trainset(ROOT / "docs" / "plan")
        self.assertTrue(trainset)
        self.assertTrue(hasattr(trainset[0], "inputs"))
        self.assertEqual(trainset[0].id, "dseed-010")

    def test_build_decompose_devset_returns_examples(self) -> None:
        devset = build_decompose_devset(ROOT / "docs" / "plan")
        self.assertTrue(devset)
        self.assertTrue(hasattr(devset[0], "inputs"))


if __name__ == "__main__":
    unittest.main()
