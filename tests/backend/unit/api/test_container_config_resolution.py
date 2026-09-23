from __future__ import annotations

import importlib
import unittest


class ContainerConfigResolutionTests(unittest.TestCase):
    def test_container_requires_an_explicit_sql_workspace(self) -> None:
        container = importlib.import_module("backend.api.di.container")

        with self.assertRaisesRegex(RuntimeError, "explicit SQL workspace"):
            container.build_default_container()


if __name__ == "__main__":
    unittest.main()
