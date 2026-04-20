from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.runtime.graph import build_series_agent_graph


class AgentGraphScaffoldTests(unittest.TestCase):
    def test_build_series_graph_returns_compiled_graph(self) -> None:
        graph = build_series_agent_graph()

        self.assertIsNotNone(graph)
        self.assertTrue(hasattr(graph, "invoke"))


if __name__ == "__main__":
    unittest.main()
