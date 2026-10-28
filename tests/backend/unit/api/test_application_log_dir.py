from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.common.app import create_app
from tests._api_fixtures import make_api_container


def _log_files() -> list[Path]:
    return [Path(handler.baseFilename) for handler in logging.getLogger("backend").handlers
            if hasattr(handler, "baseFilename")]


class ApplicationLogDirTests(unittest.TestCase):
    def test_defaults_to_logs_under_root_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_dir = Path(directory)
            with TestClient(create_app(make_api_container(root_dir=root_dir))):
                self.assertIn((root_dir / "logs" / "app.jsonl").resolve(), [path.resolve() for path in _log_files()])
            self.assertNotIn((root_dir / "logs" / "app.jsonl").resolve(), [path.resolve() for path in _log_files()])

    def test_host_log_dir_keeps_root_dir_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as config, tempfile.TemporaryDirectory() as data:
            root_dir, log_dir = Path(config), Path(data) / "logs"
            with TestClient(create_app(make_api_container(root_dir=root_dir, log_dir=log_dir))):
                self.assertTrue((log_dir / "app.jsonl").is_file())
                self.assertFalse((root_dir / "logs").exists())
            self.assertNotIn((log_dir / "app.jsonl").resolve(), [path.resolve() for path in _log_files()])


if __name__ == "__main__":
    unittest.main()
