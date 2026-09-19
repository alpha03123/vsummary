from __future__ import annotations

import importlib
import unittest


class ContainerConfigResolutionTests(unittest.TestCase):
    def test_container_import_has_no_default_workspace_side_effect(self) -> None:
        container = importlib.import_module("backend.api.di.container")

        self.assertFalse(hasattr(container, "ROOT"))
        with self.assertRaisesRegex(RuntimeError, "explicit SQL workspace"):
            container.build_default_container()


if __name__ == "__main__":
    unittest.main()
