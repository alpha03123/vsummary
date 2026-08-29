from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from updater.update import _candidate_locations, _recover_incomplete_transaction, run_update


class UpdaterTests(unittest.TestCase):
    def test_same_manifest_versions_do_not_download_or_modify_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = {
                "version": "v1",
                "app": {"version": "v1"},
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

    def test_missing_delta_requires_full_package_without_modifying_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "old.py").write_text("old", encoding="utf-8")
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

            manifest_path = _write_manifest(
                root,
                app_version="v2",
                full_url="https://example.test/vsummary-full-cpu-v1.7z",
            )

            result = run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertFalse(result.changed)
            self.assertTrue(result.requires_full_package)
            self.assertEqual((root / "src" / "old.py").read_text(encoding="utf-8"), "old")
            self.assertIn("No applicable delta", "\n".join(result.messages))
            installed = json.loads(installed_path.read_text(encoding="utf-8"))
            self.assertEqual(installed["app_version"], "v1")

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
                    "changes.json": json.dumps(_changes("v1", "v2", {"src/old.py": "new"})),
                },
            )
            delta_two = root / "release" / "v2-to-v3.zip"
            _write_zip(
                delta_two,
                {
                    "src/new.py": "latest",
                    "changes.json": json.dumps(_changes("v2", "v3", {"src/new.py": "latest"}, added=True)),
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

    def test_runtime_delta_requires_full_package(self) -> None:
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
                    "changes.json": json.dumps(_changes("v1", "v2", {"runtime/python.exe": "new"})),
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
            self.assertTrue(result.requires_full_package)
            self.assertEqual((root / "runtime" / "python.exe").read_text(encoding="utf-8"), "old")
            self.assertIn("Runtime changed", "\n".join(result.messages))

    def test_delta_failure_rolls_back_all_modified_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "first.py").write_text("old-first", encoding="utf-8")
            (root / "src" / "second.py").write_text("old-second", encoding="utf-8")
            installed_path = root / "updater" / "installed.json"
            installed_path.parent.mkdir()
            installed_path.write_text(json.dumps({"variant": "cpu", "app_version": "v1"}), encoding="utf-8")
            delta = root / "release" / "v1-to-v2.zip"
            _write_zip(
                delta,
                {
                    "src/first.py": "new-first",
                    "src/second.py": "new-second",
                    "changes.json": json.dumps(
                        _changes("v1", "v2", {"src/first.py": "new-first", "src/second.py": "new-second"})
                    ),
                },
            )
            manifest = {
                "version": "v2",
                "app": {"version": "v2"},
                "deltas": {"cpu": {"v1": {"from": "v1", "to": "v2", **_asset(delta)}}},
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            original_copy = __import__("shutil").copy2
            copied_targets: list[Path] = []

            def fail_second_target(source: str | Path, destination: str | Path, *args: object, **kwargs: object) -> str:
                target = Path(destination)
                if target.parent == root / "src":
                    copied_targets.append(target)
                    if len(copied_targets) == 2:
                        raise OSError("simulated write failure")
                return original_copy(source, destination, *args, **kwargs)

            with patch("updater.update.shutil.copy2", side_effect=fail_second_target):
                with self.assertRaises(OSError):
                    run_update(root=root, manifest_url=str(manifest_path), variant="cpu")

            self.assertEqual((root / "src" / "first.py").read_text(encoding="utf-8"), "old-first")
            self.assertEqual((root / "src" / "second.py").read_text(encoding="utf-8"), "old-second")
            self.assertFalse((root / "updater" / "transaction").exists())
            self.assertEqual(json.loads(installed_path.read_text(encoding="utf-8"))["app_version"], "v1")

    def test_startup_recovers_interrupted_delta_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "src" / "value.py"
            target.parent.mkdir()
            target.write_text("partial-new", encoding="utf-8")
            backup = root / "updater" / "transaction" / "backup" / "src" / "value.py"
            backup.parent.mkdir(parents=True)
            backup.write_text("old", encoding="utf-8")
            installed = root / "updater" / "installed.json"
            installed.write_text(json.dumps({"app_version": "v2"}), encoding="utf-8")
            (root / "updater" / "transaction" / "transaction.json").write_text(
                json.dumps({"state": "applying", "installed": {"app_version": "v1"}, "backups": ["src/value.py"], "created": []}),
                encoding="utf-8",
            )

            _recover_incomplete_transaction(root)

            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(json.loads(installed.read_text(encoding="utf-8"))["app_version"], "v1")
            self.assertFalse((root / "updater" / "transaction").exists())

    def test_github_download_candidates_fall_back_to_origin(self) -> None:
        original = "https://github.com/alpha03123/vsummary/releases/download/v1/full.7z"

        candidates = _candidate_locations(original, ("https://mirror-one.example/", "https://mirror-two.example/"))

        self.assertEqual(candidates, (
            "https://mirror-one.example/" + original,
            "https://mirror-two.example/" + original,
            original,
        ))

    def test_reads_bom_prefixed_packaging_json_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = {
                "version": "v1",
                "app": {"version": "v1"},
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
                "app": {"version": "v1"},
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
    full_url: str = "unused",
) -> Path:
    manifest = {
        "version": app_version,
        "app": {"version": app_version},
        "runtime": {"cpu": {}},
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


def _changes(from_version: str, to_version: str, files: dict[str, str], *, added: bool = False) -> dict[str, object]:
    paths = sorted(files)
    return {
        "from": from_version,
        "to": to_version,
        "added": paths if added else [],
        "modified": [] if added else paths,
        "deleted": [],
        "files": {path: hashlib.sha256(content.encode("utf-8")).hexdigest() for path, content in files.items()},
    }


if __name__ == "__main__":
    unittest.main()
