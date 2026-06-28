from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


class ContainerConfigResolutionTests(unittest.TestCase):
    def test_container_import_creates_settings_from_example_when_missing(self) -> None:
        container = importlib.import_module("backend.api.di.container")
        example_content = "example settings"

        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            config_dir = root_dir / "config"
            config_dir.mkdir()
            example_path = config_dir / "settings.toml.example"
            example_path.write_text(example_content, encoding="utf-8")
            start_path = root_dir / "src" / "backend" / "api" / "di" / "container.py"
            start_path.parent.mkdir(parents=True)
            start_path.write_text("", encoding="utf-8")

            resolved_root = container._resolve_root_dir(start_path)

            config_path = config_dir / "settings.toml"
            self.assertEqual(resolved_root, root_dir)
            self.assertTrue(config_path.exists())
            self.assertEqual(config_path.read_text(encoding="utf-8"), example_content)


if __name__ == "__main__":
    unittest.main()
