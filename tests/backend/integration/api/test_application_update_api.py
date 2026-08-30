from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.http.app import create_app


class ApplicationUpdateApiTests(unittest.TestCase):
    def test_source_installation_returns_non_interactive_source_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with TestClient(create_app(SimpleNamespace(root_dir=Path(temp_dir)))) as client:
                response = client.get("/api/application-update")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["installation_kind"], "source")
        self.assertEqual(response.json()["current_version"], "v.Source")
        self.assertFalse(response.json()["update_available"])

    def test_pack_status_and_apply_reuse_the_delta_update_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _prepare_pack(root)
            with TestClient(create_app(SimpleNamespace(root_dir=root))) as client:
                status_response = client.get("/api/application-update")

                self.assertEqual(status_response.status_code, 200)
                self.assertEqual(status_response.json()["current_version"], "v0.3.9")
                self.assertEqual(status_response.json()["latest_version"], "v0.4.0")
                self.assertTrue(status_response.json()["update_available"])
                self.assertTrue(status_response.json()["can_apply"])

                with patch("backend.api.routes.settings.schedule_update", return_value=10) as schedule:
                    apply_response = client.post("/api/application-update/apply")

                self.assertEqual(apply_response.status_code, 200)
                self.assertEqual(apply_response.json(), {"target_version": "v0.4.0", "restart_after_seconds": 10})
                schedule.assert_called_once()


def _prepare_pack(root: Path) -> None:
    (root / "runtime").mkdir()
    (root / "runtime" / "python.exe").write_text("runtime", encoding="utf-8")
    (root / "VERSION").write_text("v0.3.9", encoding="utf-8")
    updater_dir = root / "updater"
    updater_dir.mkdir()
    (updater_dir / "apply_and_restart.py").write_text("", encoding="utf-8")
    (updater_dir / "installed.json").write_text(
        json.dumps({"variant": "cpu", "app_version": "v0.3.9"}),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "version": "v0.4.0",
            "app": {"version": "v0.4.0"},
            "deltas": {"cpu": {"v0.3.9": {"from": "v0.3.9", "to": "v0.4.0"}}},
        }),
        encoding="utf-8",
    )
    (updater_dir / "config.json").write_text(
        json.dumps({"manifest_url": str(manifest_path)}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
