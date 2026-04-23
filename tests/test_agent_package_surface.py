from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class AgentPackageSurfaceTests(unittest.TestCase):
    def test_old_compaction_probe_is_removed_and_explicit_module_paths_remain(self) -> None:
        self.assertFalse((ROOT / "scripts" / "run_semantic_compaction_probe.py").exists())

        session_store_module = importlib.import_module("backend.agent.session.store")
        memory_context_module = importlib.import_module("backend.agent.memory.context")
        session_package = importlib.import_module("backend.agent.session")
        memory_package = importlib.import_module("backend.agent.memory")

        self.assertTrue(hasattr(session_store_module, "FileAgentSessionStore"))
        self.assertTrue(hasattr(memory_context_module, "AgentContext"))
        self.assertFalse(hasattr(session_package, "FileAgentSessionStore"))
        self.assertFalse(hasattr(memory_package, "AgentMemoryStore"))


if __name__ == "__main__":
    unittest.main()
