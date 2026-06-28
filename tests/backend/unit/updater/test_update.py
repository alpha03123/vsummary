from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from updater.update import run_update


class UpdaterTests(unittest.TestCase):
    def test_same_manifest_versions_do_not_download_or_modify_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = {
                "version": "v1",
                "app": {"version": "v1", "url": "unused", "sha256": "0" * 64, "size": 0},
                "runtime": {
                    "cpu": {"id": "runtime-cpu-a", "url": "unused", "sha256": "0" * 64, "size": 0}
                },
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps({"variant": "cpu", "app_version": "v1", "runtime_id": "runtime-cpu-a"}),
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
                        "runtime_id": "runtime-cpu-a",
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

    def test_runtime_update_replaces_runtime_when_runtime_id_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "python.exe").write_text("old", encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(
                json.dumps({"variant": "cpu", "app_version": "v1", "runtime_id": "runtime-cpu-a"}),
                encoding="utf-8",
            )

            runtime_zip = root / "release" / "vsummary-runtime-cpu-b.zip"
            _write_zip(runtime_zip, {"python.exe": "new", "Lib/site-packages/pkg.txt": "pkg"})
            manifest_path = _write_manifest(
                root,
                app_version="v1",
                runtime_zip=runtime_zip,
                runtime_id="runtime-cpu-b",
            )

            result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertTrue(result.changed)
            self.assertEqual((root / "runtime" / "python.exe").read_text(encoding="utf-8"), "new")
            self.assertEqual((root / "runtime" / "Lib" / "site-packages" / "pkg.txt").read_text(encoding="utf-8"), "pkg")
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            self.assertEqual(installed["runtime_id"], "runtime-cpu-b")


def _write_manifest(
    root: Path,
    *,
    app_version: str = "v1",
    app_zip: Path | None = None,
    runtime_zip: Path | None = None,
    runtime_id: str = "runtime-cpu-a",
) -> Path:
    app_asset = _asset(app_zip) if app_zip else {"url": "unused", "sha256": "0" * 64, "size": 0}
    runtime_asset = (
        {"id": runtime_id, **_asset(runtime_zip)}
        if runtime_zip
        else {"id": runtime_id, "url": "unused", "sha256": "0" * 64, "size": 0}
    )
    manifest = {
        "version": app_version,
        "app": {"version": app_version, **app_asset},
        "runtime": {"cpu": runtime_asset},
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
