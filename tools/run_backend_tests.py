"""Run backend tests against a disposable, migrated managed MySQL instance."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from backend.local.persistence.managed_mysql import ManagedLocalMySql


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysql-home", type=Path, required=True)
    args, pytest_args = parser.parse_known_args()
    with TemporaryDirectory(prefix="vsummary-tests-") as directory:
        runtime = ManagedLocalMySql(mysql_home=args.mysql_home, data_root=Path(directory))
        try:
            options = runtime.start_and_migrate()
            env = os.environ.copy()
            env["VSUMMARY_TEST_MYSQL_URL"] = options.url
            env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT)))
            return subprocess.call(
                [sys.executable, "-m", "pytest", *(pytest_args or ["tests/backend", "-q"])],
                cwd=ROOT,
                env=env,
            )
        finally:
            runtime.stop()


if __name__ == "__main__":
    raise SystemExit(main())
