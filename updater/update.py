from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


INSTALLED_PATH = Path("updater") / "installed.json"
CONFIG_PATH = Path("updater") / "config.json"
DOWNLOADS_DIR = Path("updater") / "downloads"
STAGING_DIR = Path("updater") / "staging"
APP_FILES_PATH = Path("updater") / "app-files.json"
PROTECTED_FILES = {
    ".env",
    "config/settings.toml",
    "updater/config.json",
    "updater/installed.json",
}
PROTECTED_PREFIXES = ("workspace/", "videos/", "data/", "runtime/")


@dataclass(frozen=True)
class UpdateResult:
    changed: bool
    app_updated: bool = False
    runtime_updated: bool = False
    messages: list[str] = field(default_factory=list)


def run_update(root: Path, manifest_url: str | None = None, variant: str | None = None) -> UpdateResult:
    root = root.resolve()
    installed = _read_json(root / INSTALLED_PATH, default={})
    config = _read_json(root / CONFIG_PATH, default={})
    selected_variant = variant or installed.get("variant") or config.get("variant")
    if not selected_variant:
        selected_variant = _infer_variant(root)
    if not selected_variant:
        raise RuntimeError("Cannot determine package variant. Pass --variant cpu or --variant gpu.")

    resolved_manifest_url = manifest_url or config.get("manifest_url")
    if not resolved_manifest_url:
        raise RuntimeError("Manifest URL is not configured. Pass --manifest or set updater/config.json.")

    manifest = _read_json_from_location(resolved_manifest_url)
    messages: list[str] = []
    app_updated = False
    runtime_updated = False

    app = manifest.get("app") or {}
    if app.get("version") and app.get("version") != installed.get("app_version"):
        messages.append(f"Updating app: {installed.get('app_version', 'unknown')} -> {app['version']}")
        app_archive = _download_asset(root, app)
        _apply_app_update(root, app_archive, installed)
        installed["app_version"] = app["version"]
        installed["app_files"] = _read_app_files(root)
        app_updated = True
    else:
        messages.append("App is already up to date.")

    runtime = ((manifest.get("runtime") or {}).get(selected_variant)) or {}
    if runtime.get("id") and runtime.get("id") != installed.get("runtime_id"):
        messages.append(f"Updating runtime: {installed.get('runtime_id', 'unknown')} -> {runtime['id']}")
        runtime_archive = _download_asset(root, runtime)
        _apply_runtime_update(root, runtime_archive, old_runtime_id=installed.get("runtime_id", "unknown"))
        installed["runtime_id"] = runtime["id"]
        runtime_updated = True
    else:
        messages.append("Runtime is already up to date.")

    installed["variant"] = selected_variant
    if app_updated or runtime_updated:
        _write_json(root / INSTALLED_PATH, installed)
        messages.append("Update complete.")
    else:
        messages.append("Already on the latest available version.")

    return UpdateResult(
        changed=app_updated or runtime_updated,
        app_updated=app_updated,
        runtime_updated=runtime_updated,
        messages=messages,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update packaged vsummary installation.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--variant", choices=("cpu", "gpu"), default=None)
    args = parser.parse_args(argv)

    try:
        result = run_update(root=args.root, manifest_url=args.manifest, variant=args.variant)
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1

    for message in result.messages:
        print(message)
    return 0


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_from_location(location: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme in ("http", "https", "file"):
        with urllib.request.urlopen(location) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(location).read_text(encoding="utf-8"))


def _download_asset(root: Path, asset: dict[str, Any]) -> Path:
    url = str(asset.get("url") or "")
    if not url:
        raise RuntimeError("Asset URL is missing.")
    expected_sha = str(asset.get("sha256") or "")
    file_name = str(asset.get("name") or Path(urllib.parse.urlparse(url).path).name)
    if not file_name:
        raise RuntimeError(f"Cannot determine asset file name from URL: {url}")

    target = root / DOWNLOADS_DIR / file_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and _sha256(target) == expected_sha:
        return target

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https", "file"):
        with urllib.request.urlopen(url) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
    else:
        shutil.copy2(Path(url), target)

    actual_sha = _sha256(target)
    if expected_sha and actual_sha != expected_sha:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 mismatch for {file_name}: expected {expected_sha}, got {actual_sha}")
    return target


def _apply_app_update(root: Path, archive_path: Path, installed: dict[str, Any]) -> None:
    staging = root / STAGING_DIR / "app"
    _reset_dir(staging)
    _extract_zip(archive_path, staging)
    new_files = _read_app_files(staging)
    if not new_files:
        new_files = _list_files(staging)

    old_files = [str(item).replace("\\", "/") for item in installed.get("app_files", [])]
    for relative_path in old_files:
        if relative_path not in new_files:
            _remove_app_file(root, relative_path)

    _copy_tree_contents(staging, root)
    _write_json(root / APP_FILES_PATH, {"files": new_files})
    shutil.rmtree(staging, ignore_errors=True)


def _apply_runtime_update(root: Path, archive_path: Path, *, old_runtime_id: str) -> None:
    staging = root / STAGING_DIR / "runtime"
    _reset_dir(staging)
    _extract_zip(archive_path, staging)

    runtime_root = root / "runtime"
    backup_root = root / "updater" / "backups" / f"runtime-{old_runtime_id}"
    if backup_root.exists():
        shutil.rmtree(backup_root)
    backup_root.parent.mkdir(parents=True, exist_ok=True)

    try:
        if runtime_root.exists():
            shutil.move(str(runtime_root), str(backup_root))
        shutil.move(str(staging), str(runtime_root))
    except Exception:
        if runtime_root.exists():
            shutil.rmtree(runtime_root, ignore_errors=True)
        if backup_root.exists():
            shutil.move(str(backup_root), str(runtime_root))
        raise
    else:
        shutil.rmtree(backup_root, ignore_errors=True)


def _extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not _is_within(target, destination.resolve()):
                raise RuntimeError(f"Unsafe archive member path: {member.filename}")
            archive.extract(member, destination)


def _copy_tree_contents(source: Path, destination: Path) -> None:
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _remove_app_file(root: Path, relative_path: str) -> None:
    normalized = relative_path.replace("\\", "/")
    if normalized in PROTECTED_FILES or normalized.startswith(PROTECTED_PREFIXES):
        return
    target = (root / normalized).resolve()
    if not _is_within(target, root.resolve()):
        raise RuntimeError(f"Refusing to remove path outside install root: {relative_path}")
    if target.is_file():
        target.unlink()
        _remove_empty_parents(target.parent, root)


def _remove_empty_parents(path: Path, root: Path) -> None:
    current = path
    while current != root and _is_within(current.resolve(), root.resolve()):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _read_app_files(root: Path) -> list[str]:
    payload = _read_json(root / APP_FILES_PATH, default={})
    files = payload.get("files", []) if isinstance(payload, dict) else []
    return [str(item).replace("\\", "/") for item in files]


def _list_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _infer_variant(root: Path) -> str:
    runtime_id_path = root / "RUNTIME"
    if runtime_id_path.is_file():
        runtime_id = runtime_id_path.read_text(encoding="utf-8").strip()
        if runtime_id.startswith("runtime-cpu-"):
            return "cpu"
        if runtime_id.startswith("runtime-gpu-"):
            return "gpu"
    return ""


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
