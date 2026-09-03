from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.api import application_update
from updater import apply_and_restart


class ApplicationUpdateLauncherTests(unittest.TestCase):
    def test_schedule_update_detaches_the_update_launcher_and_writes_a_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            updater_dir = root / "updater"
            updater_dir.mkdir()
            (updater_dir / "apply_and_restart.py").write_text("", encoding="utf-8")

            with (
                patch.object(application_update, "_has_active_tasks", return_value=False),
                patch.object(application_update, "_restart_scheduled", False),
                patch.object(application_update, "_load_pack_update_preparer", return_value=lambda *args, **kwargs: None),
                patch.object(application_update.subprocess, "Popen") as popen,
                patch.object(application_update, "Thread") as thread,
            ):
                application_update.schedule_update(root=root, variant="cpu", container=SimpleNamespace())

            arguments = popen.call_args.kwargs
            self.assertEqual(arguments["cwd"], root)
            self.assertEqual(arguments["stdin"], subprocess.DEVNULL)
            self.assertEqual(arguments["stderr"], subprocess.STDOUT)
            self.assertNotEqual(arguments["creationflags"], 0)
            self.assertTrue((updater_dir / "update.log").is_file())
            thread.assert_called_once()

    def test_update_restarts_the_pack_when_waiting_for_the_old_process_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "start.bat").write_text("", encoding="utf-8")

            with (
                patch.object(apply_and_restart, "_wait_for_process_exit", return_value=False),
                patch.object(apply_and_restart, "_restart_pack") as restart,
            ):
                with self.assertRaisesRegex(RuntimeError, "Timed out"):
                    apply_and_restart.apply_and_restart(root=root, wait_for_pid=123, variant="cpu")

            restart.assert_called_once_with(root)


if __name__ == "__main__":
    unittest.main()
