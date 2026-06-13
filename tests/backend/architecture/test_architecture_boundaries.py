from __future__ import annotations

import subprocess
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[3]


def test_import_contracts() -> None:
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    src_path = str(_REPO_ROOT / "src")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else os.pathsep.join([src_path, existing_pythonpath])
    result = subprocess.run(
        ["lint-imports", "--config", str(_REPO_ROOT / ".importlinter")],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, (
        "import-linter contract violations:\n" + result.stdout + result.stderr
    )
