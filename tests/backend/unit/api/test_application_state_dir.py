from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.common.app import create_app
from tests._api_fixtures import make_api_container


def _log_files() -> list[Path]:
    return [Path(handler.baseFilename).resolve() for handler in logging.getLogger("backend").handlers
            if hasattr(handler, "baseFilename")]


class ApplicationStateDirTests(unittest.TestCase):
    def test_logs_default_to_root_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_dir = Path(directory)
            log_file = (root_dir / "logs" / "app.jsonl").resolve()
            with TestClient(create_app(make_api_container(root_dir=root_dir))):
                self.assertIn(log_file, _log_files())
            self.assertNotIn(log_file, _log_files())

    def test_host_state_dir_keeps_root_dir_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as config, tempfile.TemporaryDirectory() as data:
            root_dir, state_dir = Path(config), Path(data)
            container = make_api_container(root_dir=root_dir, state_dir=state_dir)
            self.assertEqual(container.state_root, state_dir)
            with TestClient(create_app(container)):
                self.assertTrue((state_dir / "logs" / "app.jsonl").is_file())
            self.assertEqual(list(root_dir.iterdir()), [])
            self.assertNotIn((state_dir / "logs" / "app.jsonl").resolve(), _log_files())

    def test_state_root_defaults_to_root_dir(self) -> None:
        self.assertEqual(make_api_container(root_dir=Path("app")).state_root, Path("app"))


if __name__ == "__main__":
    unittest.main()
