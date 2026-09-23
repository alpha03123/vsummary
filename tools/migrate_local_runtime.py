"""Copy a stopped Local runtime into a project-owned data directory."""

from __future__ import annotations

import argparse
import json
import shutil
import socket
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy a stopped VSummary Local runtime without deleting the source.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    target_root = args.target_root.expanduser().resolve()
    if source_root == target_root:
        raise ValueError("Source and target runtime directories must differ.")
    if not source_root.is_dir():
        raise FileNotFoundError(f"Source runtime directory does not exist: {source_root}")
    if target_root.exists():
        raise FileExistsError(f"Target runtime directory already exists: {target_root}")
    _require_database_stopped(source_root)

    staging_root = target_root.with_name(f"{target_root.name}.migrating")
    if staging_root.exists():
        raise FileExistsError(f"Migration staging directory already exists: {staging_root}")
    try:
        shutil.copytree(source_root, staging_root, ignore=_ignore_runtime_locks)
        _validate_runtime_copy(source_root, staging_root)
        staging_root.rename(target_root)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    print(json.dumps({"source_root": str(source_root), "target_root": str(target_root), "status": "copied"}))
    return 0


def _require_database_stopped(source_root: Path) -> None:
    runtime_path = source_root / "mysql" / "runtime.json"
    if not runtime_path.is_file():
        return
    payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    port = payload.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError(f"Runtime metadata has an invalid MySQL port: {runtime_path}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        if client.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError("Stop the VSummary backend before copying its MySQL runtime.")


def _ignore_runtime_locks(directory: str, names: list[str]) -> set[str]:
    current = Path(directory)
    if current.name == "run" and current.parent.name == "mysql":
        return set(names)
    return set()


def _validate_runtime_copy(source_root: Path, target_root: Path) -> None:
    for relative_path in ("mysql/data", "mysql/runtime.json", "mysql/vsummary_app.dpapi", "blobs/objects"):
        source = source_root / relative_path
        target = target_root / relative_path
        if source.exists() != target.exists():
            raise RuntimeError(f"Runtime copy is incomplete: {relative_path}")


if __name__ == "__main__":
    raise SystemExit(main())
