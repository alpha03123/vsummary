from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from updater.update import RuntimeCompatibility, run_update


class UpdaterTests(unittest.TestCase):
    def test_same_manifest_versions_do_not_download_or_modify_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = {
                "version": "v1",
                "app": {"version": "v1", "url": "unused", "sha256": "0" * 64, "size": 0},
                "runtime": {"cpu": {}},
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps({"variant": "cpu", "app_version": "v1"}),
                encoding="utf-8",
            )
            marker = root / "src" / "marker.txt"
            marker.parent.mkdir()
            marker.write_text("keep", encoding="utf-8")

            result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertFalse(result.changed)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_app_update_replaces_app_files_and_preserves_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "old.py").write_text("old", encoding="utf-8")
            (root / "workspace").mkdir()
            (root / "workspace" / "note.md").write_text("user", encoding="utf-8")
            (root / "config").mkdir()
            (root / "config" / "settings.toml").write_text("user_config = true", encoding="utf-8")
            (root / ".env").write_text("USER=1", encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps(
                    {
                        "variant": "cpu",
                        "app_version": "v1",
                        "app_files": ["src/old.py"],
                    }
                ),
                encoding="utf-8",
            )

            app_zip = root / "release" / "vsummary-app-v2.zip"
            _write_zip(
                app_zip,
                {
                    "src/new.py": "new",
                    "config/settings.toml.example": "example",
                    "updater/app-files.json": json.dumps(
                        {"files": ["src/new.py", "config/settings.toml.example"]}
                    ),
                },
            )
            manifest_path = _write_manifest(root, app_zip=app_zip, app_version="v2")

            result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertTrue(result.changed)
            self.assertFalse((root / "src" / "old.py").exists())
            self.assertEqual((root / "src" / "new.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((root / "workspace" / "note.md").read_text(encoding="utf-8"), "user")
            self.assertEqual((root / "config" / "settings.toml").read_text(encoding="utf-8"), "user_config = true")
            self.assertEqual((root / ".env").read_text(encoding="utf-8"), "USER=1")
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            self.assertEqual(installed["app_version"], "v2")
            self.assertEqual(installed["app_files"], ["src/new.py", "config/settings.toml.example"])

    def test_incompatible_runtime_reports_full_package_required_without_downloading_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            runtime.mkdir()
            (root / "src").mkdir()
            (root / "src" / "old.py").write_text("old", encoding="utf-8")
            (runtime / "python.exe").write_text("old", encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps(
                    {
                        "variant": "cpu",
                        "app_version": "v1",
                        "app_files": ["src/old.py"],
                    }
                ),
                encoding="utf-8",
            )

            app_zip = root / "release" / "vsummary-app-v2.zip"
            _write_zip(
                app_zip,
                {
                    "src/new.py": "new",
                    "updater/app-files.json": json.dumps({"files": ["src/new.py"]}),
                },
            )
            manifest_path = _write_manifest(
                root,
                app_version="v2",
                app_zip=app_zip,
                full_url="https://example.test/vsummary-full-cpu-v1.7z",
                requirements={"python": ">=3.11,<3.12", "packages": ["fastapi>=0.115,<1"]},
            )

            with patch("updater.update._check_runtime_requirements", return_value=RuntimeCompatibility(False, ["fastapi is missing"])):
                result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertFalse(result.changed)
            self.assertTrue(result.requires_full_package)
            self.assertEqual((root / "runtime" / "python.exe").read_text(encoding="utf-8"), "old")
            self.assertEqual((root / "src" / "old.py").read_text(encoding="utf-8"), "old")
            self.assertFalse((root / "src" / "new.py").exists())
            self.assertIn("does not satisfy", "\n".join(result.messages))
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            self.assertEqual(installed["app_version"], "v1")

    def test_updates_app_when_current_runtime_satisfies_manifest_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "old.py").write_text("old", encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps({"variant": "cpu", "app_version": "v1", "app_files": ["src/old.py"]}),
                encoding="utf-8",
            )
            app_zip = root / "release" / "vsummary-app-v2.zip"
            _write_zip(app_zip, {"src/new.py": "new", "updater/app-files.json": json.dumps({"files": ["src/new.py"]})})
            manifest_path = _write_manifest(
                root,
                app_version="v2",
                app_zip=app_zip,
                requirements={"python": ">=3.11,<3.12", "packages": ["fastapi>=0.115,<1"]},
            )

            with patch("updater.update._check_runtime_requirements", return_value=RuntimeCompatibility(True)):
                result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertTrue(result.changed)
            self.assertEqual((root / "src" / "new.py").read_text(encoding="utf-8"), "new")
            self.assertIn("Current runtime satisfies", "\n".join(result.messages))
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            self.assertEqual(installed["app_version"], "v2")

    def test_applies_multiple_adjacent_deltas_to_reach_target_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "old.py").write_text("old", encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps({"variant": "cpu", "app_version": "v1", "app_files": ["src/old.py"]}),
                encoding="utf-8",
            )

            delta_one = root / "release" / "v1-to-v2.zip"
            _write_zip(
                delta_one,
                {
                    "src/old.py": "new",
                    "changes.json": json.dumps({"from": "v1", "to": "v2", "modified": ["src/old.py"]}),
                },
            )
            delta_two = root / "release" / "v2-to-v3.zip"
            _write_zip(
                delta_two,
                {
                    "src/new.py": "latest",
                    "changes.json": json.dumps({"from": "v2", "to": "v3", "added": ["src/new.py"]}),
                },
            )
            manifest = {
                "version": "v3",
                "app": {"version": "v3"},
                "runtime": {"cpu": {}},
                "deltas": {
                    "cpu": {
                        "v1": {"from": "v1", "to": "v2", **_asset(delta_one)},
                        "v2": {"from": "v2", "to": "v3", **_asset(delta_two)},
                    }
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertTrue(result.changed)
            self.assertTrue(result.app_updated)
            self.assertFalse(result.runtime_updated)
            self.assertEqual((root / "src" / "old.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((root / "src" / "new.py").read_text(encoding="utf-8"), "latest")
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            self.assertEqual(installed["app_version"], "v3")

    def test_runtime_delta_is_staged_for_update_batch_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "runtime").mkdir()
            (root / "runtime" / "python.exe").write_text("old", encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(json.dumps({"variant": "cpu", "app_version": "v1"}), encoding="utf-8")
            delta = root / "release" / "v1-to-v2-runtime.zip"
            _write_zip(
                delta,
                {
                    "runtime/python.exe": "new",
                    "changes.json": json.dumps(
                        {"from": "v1", "to": "v2", "modified": ["runtime/python.exe"]}
                    ),
                },
            )
            manifest = {
                "version": "v2",
                "app": {"version": "v2"},
                "runtime": {"cpu": {}},
                "deltas": {
                    "cpu": {
                        "v1": {"from": "v1", "to": "v2", "runtime": True, **_asset(delta)},
                    }
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertFalse(result.changed)
            self.assertTrue(result.pending_delta)
            self.assertEqual((root / "runtime" / "python.exe").read_text(encoding="utf-8"), "old")
            script = (root / "updater" / "apply-pending-delta.bat").read_text(encoding="ascii")
            self.assertIn("runtime\\python.exe", script)
            pending = json.loads((root / "updater" / "installed.pending.json").read_text(encoding="utf-8"))
            self.assertEqual(pending["app_version"], "v2")

    def test_reads_bom_prefixed_packaging_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = {
                "version": "v1",
                "app": {"version": "v1", "url": "unused", "sha256": "0" * 64, "size": 0},
                "runtime": {"gpu": {}},
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8-sig")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps({"variant": "gpu", "app_version": "v1"}),
                encoding="utf-8-sig",
            )

            result = run_update(root=root, manifest_url=str(manifest_path))

            self.assertFalse(result.changed)
            self.assertIn("App is already up to date.", result.messages)

    def test_infers_variant_from_bom_prefixed_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "RUNTIME").write_text("gpu", encoding="utf-8-sig")
            config_path = root / "updater" / "config.json"
            config_path.parent.mkdir()
            installed_path = root / "updater" / "installed.json"
            installed_path.write_text(
                json.dumps({"app_version": "v1"}),
                encoding="utf-8",
            )
            manifest = {
                "version": "v1",
                "app": {"version": "v1", "url": "unused", "sha256": "0" * 64, "size": 0},
                "runtime": {"gpu": {}},
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            config_path.write_text(json.dumps({"manifest_url": str(manifest_path)}), encoding="utf-8")

            result = run_update(root=root)

            self.assertFalse(result.changed)
            self.assertIn("Runtime was retained.", result.messages)


def _write_manifest(
    root: Path,
    *,
    app_version: str = "v1",
    app_zip: Path | None = None,
    full_url: str = "unused",
    requirements: dict[str, object] | None = None,
) -> Path:
    app_asset = _asset(app_zip) if app_zip else {"url": "unused", "sha256": "0" * 64, "size": 0}
    manifest = {
        "version": app_version,
        "app": {"version": app_version, **app_asset},
        "runtime": {"cpu": {**({"requirements": requirements} if requirements else {})}},
        "full": {"cpu": {"url": full_url}},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _write_zip(path: Path, files: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def _asset(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "url": str(path),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


if __name__ == "__main__":
    unittest.main()
