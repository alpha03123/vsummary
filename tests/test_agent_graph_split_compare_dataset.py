from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.split_compare_dataset import (
    build_split_compare_devset,
    build_split_compare_trainset,
    load_split_compare_records,
)


class AgentGraphSplitCompareDatasetTests(unittest.TestCase):
    def test_load_split_compare_records_reads_seed_and_variant_markdown(self) -> None:
        records = load_split_compare_records(ROOT / "docs" / "plan")

        self.assertGreaterEqual(len(records), 20)
        self.assertTrue(any(record["id"] == "cseed-001" for record in records))
        self.assertTrue(any(record["id"] == "cvar-020" for record in records))

    def test_build_split_compare_trainset_returns_examples(self) -> None:
        trainset = build_split_compare_trainset(ROOT / "docs" / "plan")
        self.assertTrue(trainset)
        self.assertTrue(hasattr(trainset[0], "inputs"))

    def test_build_split_compare_devset_returns_examples(self) -> None:
        devset = build_split_compare_devset(ROOT / "docs" / "plan")
        self.assertTrue(devset)
        self.assertTrue(hasattr(devset[0], "inputs"))


if __name__ == "__main__":
    unittest.main()
