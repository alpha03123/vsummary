"""Generate candidate dead-code reports without modifying project source files.

The report combines Vulture for Python and Knip for the frontend. Both tools
are conservative candidates generators: dynamic imports, ORM models, FastAPI
routes and test fixtures require a human review before deletion.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report low-reference code candidates.")
    parser.add_argument("--output", type=Path, default=REPOSITORY_ROOT / "temp" / "reference-audit.md")
    parser.add_argument("--python-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    args = parser.parse_args(argv)
    if args.python_only and args.frontend_only:
        parser.error("--python-only and --frontend-only cannot be combined.")

    sections = ["# Reference Audit", "", "Candidates only. Review every item before deletion.", ""]
    if not args.frontend_only:
        sections.extend(_run_python_audit())
    if not args.python_only:
        sections.extend(_run_frontend_audit())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    print(args.output)
    return 0


def _run_python_audit() -> list[str]:
    command = [sys.executable, "-m", "vulture", "src/backend", "--min-confidence", "80"]
    result = subprocess.run(command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, check=False)
    return _section("Python: Vulture", command, result.stdout, result.stderr, result.returncode)


def _run_frontend_audit() -> list[str]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        return ["## Frontend: Knip", "", "npm is unavailable.", ""]
    command = [npm, "exec", "--", "knip", "--config", "knip.json"]
    result = subprocess.run(command, cwd=REPOSITORY_ROOT / "src" / "frontend", text=True, capture_output=True, check=False)
    return _section("Frontend: Knip", command, result.stdout, result.stderr, result.returncode)


def _section(title: str, command: list[str], stdout: str, stderr: str, returncode: int) -> list[str]:
    output = stdout.strip() or "No candidates reported."
    if stderr.strip():
        output = f"{output}\n\nDiagnostics:\n{stderr.strip()}"
    return [f"## {title}", "", f"Command: `{' '.join(command)}`", "", f"Exit code: {returncode}", "", "```text", output, "```", ""]


if __name__ == "__main__":
    raise SystemExit(main())
