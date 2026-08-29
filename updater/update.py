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
TRANSACTION_DIR = Path("updater") / "transaction"
TRANSACTION_PATH = TRANSACTION_DIR / "transaction.json"
PROTECTED_FILES = {
    ".env",
    "config/settings.toml",
    "updater/config.json",
    "updater/installed.json",
}
PROTECTED_PREFIXES = ("workspace/", "videos/", "data/")
DEFAULT_GITHUB_MIRRORS = (
    "https://ghfast.top/",
    "https://gh-proxy.com/",
)
GITHUB_HOSTS = {"github.com", "api.github.com", "raw.githubusercontent.com", "objects.githubusercontent.com"}


@dataclass(frozen=True)
class UpdateResult:
    changed: bool
    app_updated: bool = False
    runtime_updated: bool = False
    requires_full_package: bool = False
    messages: list[str] = field(default_factory=list)


def run_update(root: Path, manifest_url: str | None = None, variant: str | None = None) -> UpdateResult:
    root = root.resolve()
    _recover_incomplete_transaction(root)
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

    mirrors = _resolve_download_mirrors(config)
    manifest = _read_json_from_location(resolved_manifest_url, mirrors=mirrors)
    messages: list[str] = []
    app_updated = False
    runtime_updated = False

    app = manifest.get("app") or {}
    target_version = str(app.get("version") or manifest.get("version") or "")
    app_needs_update = target_version and target_version != installed.get("app_version")
    if app_needs_update:
        delta_chain = _find_delta_chain(
            manifest.get("deltas"),
            variant=selected_variant,
            current_version=str(installed.get("app_version") or ""),
            target_version=target_version,
        )
        if delta_chain:
            if any(bool(delta.get("runtime")) for delta in delta_chain):
                full = ((manifest.get("full") or {}).get(selected_variant)) or {}
                full_url = full.get("url") or "the latest full package"
                messages.append(f"Runtime changed. Download and reinstall the full package: {full_url}")
                return UpdateResult(changed=False, requires_full_package=True, messages=messages)
            prepared_deltas = _prepare_delta_chain(root, delta_chain, mirrors)
            _apply_delta_transaction(root, prepared_deltas, installed, selected_variant)
            installed["app_version"] = target_version
            installed["app_files"] = _read_app_files(root)
            installed["variant"] = selected_variant
            _write_json(root / INSTALLED_PATH, installed)
            _commit_transaction(root)
            app_updated = True
            messages.append("Delta update complete.")
            messages.append("Runtime was retained.")
            return UpdateResult(
                changed=True,
                app_updated=True,
                runtime_updated=False,
                messages=messages,
            )
        full = ((manifest.get("full") or {}).get(selected_variant)) or {}
        full_url = full.get("url") or "the latest full package"
        messages.append(
            f"No applicable delta is available for {installed.get('app_version', 'unknown')} -> {target_version}. "
            f"Download and reinstall the full package: {full_url}"
        )
        return UpdateResult(changed=False, requires_full_package=True, messages=messages)
    else:
        messages.append("App is already up to date.")

    messages.append("Runtime was retained.")

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
    if result.requires_full_package:
        return 2
    return 0


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_json_from_location(location: str, *, mirrors: tuple[str, ...] = ()) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme in ("http", "https", "file"):
        errors: list[str] = []
        for candidate in _candidate_locations(location, mirrors):
            try:
                with urllib.request.urlopen(candidate, timeout=20) as response:
                    return json.loads(response.read().decode("utf-8-sig"))
            except Exception as error:
                errors.append(f"{candidate}: {error}")
        raise RuntimeError("Unable to download update manifest: " + "; ".join(errors))
    return json.loads(Path(location).read_text(encoding="utf-8-sig"))


def _download_asset(root: Path, asset: dict[str, Any], *, mirrors: tuple[str, ...] = ()) -> Path:
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
    if parsed.scheme not in ("http", "https", "file"):
        shutil.copy2(Path(url), target)
        return _validate_download(target, expected_sha, file_name)

    errors: list[str] = []
    for candidate in _candidate_locations(url, mirrors):
        try:
            with urllib.request.urlopen(candidate, timeout=60) as response, target.open("wb") as output:
                shutil.copyfileobj(response, output)
            return _validate_download(target, expected_sha, file_name)
        except Exception as error:
            target.unlink(missing_ok=True)
            errors.append(f"{candidate}: {error}")
    raise RuntimeError(f"Unable to download {file_name}: " + "; ".join(errors))


def _validate_download(target: Path, expected_sha: str, file_name: str) -> Path:
    actual_sha = _sha256(target)
    if expected_sha and actual_sha != expected_sha:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 mismatch for {file_name}: expected {expected_sha}, got {actual_sha}")
    return target


def _resolve_download_mirrors(config: Any) -> tuple[str, ...]:
    configured = config.get("download_mirrors") if isinstance(config, dict) else None
    candidates = configured if isinstance(configured, list) else DEFAULT_GITHUB_MIRRORS
    mirrors: list[str] = []
    for value in candidates:
        prefix = str(value).strip()
        parsed = urllib.parse.urlparse(prefix)
        if parsed.scheme != "https" or not parsed.netloc:
            continue
        normalized = prefix.rstrip("/") + "/"
        if normalized not in mirrors:
            mirrors.append(normalized)
    return tuple(mirrors)


def _candidate_locations(location: str, mirrors: tuple[str, ...]) -> tuple[str, ...]:
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme != "https" or parsed.hostname not in GITHUB_HOSTS:
        return (location,)
    return tuple(prefix + location for prefix in mirrors) + (location,)


def _prepare_delta_chain(
    root: Path,
    delta_chain: list[dict[str, Any]],
    mirrors: tuple[str, ...],
) -> list[tuple[Path, dict[str, Any]]]:
    staging = root / STAGING_DIR / "delta"
    _reset_dir(staging)
    prepared: list[tuple[Path, dict[str, Any]]] = []
    for index, delta in enumerate(delta_chain):
        from_version = str(delta.get("from") or "")
        to_version = str(delta.get("to") or "")
        stage = staging / str(index)
        _extract_zip(_download_asset(root, delta, mirrors=mirrors), stage)
        changes = _read_delta_changes(stage, from_version, to_version)
        _validate_delta_payload(stage, changes)
        prepared.append((stage, changes))
    return prepared


def _apply_delta_transaction(
    root: Path,
    prepared_deltas: list[tuple[Path, dict[str, Any]]],
    installed: dict[str, Any],
    variant: str,
) -> None:
    transaction_dir = root / TRANSACTION_DIR
    _reset_dir(transaction_dir)
    transaction = {
        "state": "applying",
        "installed": installed,
        "variant": variant,
        "backups": [],
        "created": [],
    }
    _write_json(root / TRANSACTION_PATH, transaction)
    try:
        for stage, changes in prepared_deltas:
            for raw_path in changes.get("deleted", []):
                relative_path = _validate_delta_path(raw_path)
                _backup_for_mutation(root, transaction, relative_path)
                _remove_file(root, relative_path)
            for relative_path in [*changes["added"], *changes["modified"]]:
                normalized_path = _validate_delta_path(relative_path)
                _backup_for_mutation(root, transaction, normalized_path)
                target = root / normalized_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage / normalized_path, target)
    except Exception:
        _rollback_transaction(root)
        raise


def _backup_for_mutation(root: Path, transaction: dict[str, Any], relative_path: str) -> None:
    target = root / relative_path
    backups = set(transaction["backups"])
    created = set(transaction["created"])
    if relative_path in backups or relative_path in created:
        return
    if target.is_file():
        backup = root / TRANSACTION_DIR / "backup" / relative_path
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        transaction["backups"].append(relative_path)
    else:
        transaction["created"].append(relative_path)
    _write_json(root / TRANSACTION_PATH, transaction)


def _commit_transaction(root: Path) -> None:
    transaction = _read_json(root / TRANSACTION_PATH, default={})
    if isinstance(transaction, dict):
        transaction["state"] = "committed"
        _write_json(root / TRANSACTION_PATH, transaction)
    shutil.rmtree(root / TRANSACTION_DIR, ignore_errors=True)


def _recover_incomplete_transaction(root: Path) -> None:
    transaction = _read_json(root / TRANSACTION_PATH, default=None)
    if not isinstance(transaction, dict):
        return
    if transaction.get("state") != "committed":
        _rollback_transaction(root)
    else:
        shutil.rmtree(root / TRANSACTION_DIR, ignore_errors=True)


def _rollback_transaction(root: Path) -> None:
    transaction = _read_json(root / TRANSACTION_PATH, default={})
    if not isinstance(transaction, dict):
        return
    for relative_path in reversed([str(path) for path in transaction.get("created", [])]):
        _remove_file(root, relative_path)
    for relative_path in reversed([str(path) for path in transaction.get("backups", [])]):
        backup = root / TRANSACTION_DIR / "backup" / relative_path
        if backup.is_file():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
    original_installed = transaction.get("installed")
    if isinstance(original_installed, dict):
        _write_json(root / INSTALLED_PATH, original_installed)
    shutil.rmtree(root / TRANSACTION_DIR, ignore_errors=True)


def _read_delta_changes(stage: Path, expected_from: str, expected_to: str) -> dict[str, Any]:
    changes = _read_json(stage / "changes.json", default=None)
    if not isinstance(changes, dict):
        raise RuntimeError("Delta package is missing changes.json.")
    if changes.get("from") != expected_from or changes.get("to") != expected_to:
        raise RuntimeError(
            "Delta base/target mismatch: "
            f"expected {expected_from} -> {expected_to}, "
            f"got {changes.get('from')} -> {changes.get('to')}"
        )
    return changes


def _is_protected_path(relative_path: str) -> bool:
    return relative_path in PROTECTED_FILES or any(relative_path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def _validate_delta_payload(stage: Path, changes: dict[str, Any]) -> None:
    added = [_validate_delta_path(path) for path in changes.get("added", [])]
    modified = [_validate_delta_path(path) for path in changes.get("modified", [])]
    deleted = [_validate_delta_path(path) for path in changes.get("deleted", [])]
    if any(_is_protected_path(path) for path in [*added, *modified, *deleted]):
        raise RuntimeError("Delta package attempts to modify protected user data.")
    files = changes.get("files")
    if not isinstance(files, dict):
        raise RuntimeError("Delta package is missing file hashes.")
    expected_paths = set([*added, *modified])
    if set(files) != expected_paths:
        raise RuntimeError("Delta file hash list does not match changed files.")
    for relative_path in expected_paths:
        source = stage / relative_path
        expected_hash = str(files.get(relative_path) or "").lower()
        if not source.is_file() or len(expected_hash) != 64 or _sha256(source) != expected_hash:
            raise RuntimeError(f"Delta payload checksum failed: {relative_path}")


def _remove_file(root: Path, relative_path: str) -> None:
    target = root / relative_path
    if target.is_file():
        target.unlink()
        _remove_empty_parents(target.parent, root)


def _extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not _is_within(target, destination.resolve()):
                raise RuntimeError(f"Unsafe archive member path: {member.filename}")
            archive.extract(member, destination)


def _validate_delta_path(value: Any) -> str:
    relative_path = str(value).replace("\\", "/")
    if not relative_path or relative_path.startswith("/") or relative_path == "changes.json":
        raise RuntimeError(f"Invalid delta path: {value}")
    candidate = Path(relative_path)
    if any(part in ("", ".", "..") for part in candidate.parts):
        raise RuntimeError(f"Invalid delta path: {value}")
    return relative_path


def _find_delta_chain(
    deltas: Any,
    *,
    variant: str,
    current_version: str,
    target_version: str,
) -> list[dict[str, Any]] | None:
    if not current_version or not target_version or current_version == target_version:
        return None
    variant_deltas = deltas.get(variant) if isinstance(deltas, dict) else None
    if not isinstance(variant_deltas, dict):
        return None

    chain: list[dict[str, Any]] = []
    version = current_version
    seen: set[str] = set()
    for _ in range(100):
        if version == target_version:
            return chain
        if version in seen:
            return None
        seen.add(version)
        raw_delta = variant_deltas.get(version)
        if not isinstance(raw_delta, dict):
            return None
        from_version = str(raw_delta.get("from") or version)
        to_version = str(raw_delta.get("to") or "")
        if from_version != version or not to_version:
            return None
        chain.append(raw_delta)
        version = to_version
    return None


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
    runtime_path = root / "RUNTIME"
    if runtime_path.is_file():
        runtime = runtime_path.read_text(encoding="utf-8-sig").strip()
        if runtime == "cpu":
            return "cpu"
        if runtime == "gpu":
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
