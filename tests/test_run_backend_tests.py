from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_script_module():
    module_path = ROOT / "scripts" / "run_backend_tests.py"
    spec = importlib.util.spec_from_file_location("run_backend_tests", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RunBackendTestsScriptTests(unittest.TestCase):
    def test_resolve_project_python_prefers_repo_venv(self) -> None:
        module = _load_script_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_python = root / ".venv" / "Scripts" / "python.exe"
            project_python.parent.mkdir(parents=True)
            project_python.write_text("", encoding="utf-8")

            resolved = module.resolve_project_python(
                root_dir=root,
                current_executable=r"C:\Python313\python.exe",
            )

        self.assertEqual(resolved, project_python)

    def test_main_reexecs_with_repo_python_before_running_unittest(self) -> None:
        module = _load_script_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project_python = root / ".venv" / "Scripts" / "python.exe"
            project_python.parent.mkdir(parents=True)
            project_python.write_text("", encoding="utf-8")

            with (
                patch.object(module, "ROOT", root),
                patch.object(module.sys, "argv", ["run_backend_tests.py", "agent"]),
                patch.object(module.sys, "executable", r"C:\Python313\python.exe"),
                patch.dict(module.os.environ, {}, clear=True),
                patch.object(module.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run_mock,
            ):
                exit_code = module.main()

        self.assertEqual(exit_code, 0)
        run_mock.assert_called_once()
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], str(project_python))
        self.assertTrue(command[1].endswith("scripts\\run_backend_tests.py"))
        self.assertEqual(command[2:], ["agent"])
        self.assertEqual(run_mock.call_args.kwargs["cwd"], root)
        self.assertEqual(
            run_mock.call_args.kwargs["env"][module.PROJECT_PYTHON_REEXEC_ENV],
            "1",
        )


if __name__ == "__main__":
    unittest.main()
