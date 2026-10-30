from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from updater import apply_and_restart


class ApplicationUpdateLauncherTests(unittest.TestCase):
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
