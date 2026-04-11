from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy_dataset import (
    build_classifier_devset,
    build_classifier_trainset,
    load_classifier_records,
)


class AgentGraphDspyDatasetTests(unittest.TestCase):
    def test_load_classifier_records_parses_seed_and_variant_markdown(self) -> None:
        records = load_classifier_records(ROOT / "docs" / "plan")

        self.assertGreaterEqual(len(records), 100)
        self.assertTrue(any(record["id"] == "seed-001" for record in records))
        self.assertTrue(any(record["id"] == "var-100" for record in records))

    def test_build_classifier_trainset_excludes_boundary_ids(self) -> None:
        trainset = build_classifier_trainset(ROOT / "docs" / "plan")
        ids = {example.id for example in trainset}

        self.assertNotIn("seed-030", ids)
        self.assertNotIn("var-099", ids)

    def test_build_classifier_devset_returns_examples(self) -> None:
        devset = build_classifier_devset(ROOT / "docs" / "plan")

        self.assertTrue(devset)
        self.assertTrue(hasattr(devset[0], "inputs"))


if __name__ == "__main__":
    unittest.main()
