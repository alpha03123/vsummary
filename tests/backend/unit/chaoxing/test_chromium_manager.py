from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from backend.chaoxing.chromium import ChaoxingChromiumManager, _run_command
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker


class ChaoxingChromiumManagerTests(unittest.TestCase):
    def test_sets_process_browser_path_to_project_browser_path(self) -> None:
        previous = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manager = ChaoxingChromiumManager(root_dir=Path(tmp), progress_tracker=InMemoryProgressTracker())

                self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(manager.browsers_dir))
        finally:
            if previous is None:
                os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
            else:
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = previous

    def test_reports_chromium_not_downloaded_when_browser_dir_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ChaoxingChromiumManager(root_dir=Path(tmp), progress_tracker=InMemoryProgressTracker())

            status = manager.get_status()

            self.assertEqual(status.key, "chaoxing-chromium")
            self.assertFalse(status.downloaded)
            self.assertEqual(status.status, "idle")
            self.assertEqual(status.local_path, str(Path(tmp) / "data" / "playwright-browsers"))

    def test_reports_chromium_downloaded_when_chromium_directory_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            browsers_dir = Path(tmp) / "data" / "playwright-browsers"
            (browsers_dir / "chromium-1223").mkdir(parents=True)
            manager = ChaoxingChromiumManager(root_dir=Path(tmp), progress_tracker=InMemoryProgressTracker())

            status = manager.get_status()

            self.assertTrue(status.downloaded)

    def test_start_download_runs_playwright_install_with_project_browser_path(self) -> None:
        calls: list[tuple[list[str], dict[str, str]]] = []

        def fake_runner(command: list[str], env: dict[str, str]) -> None:
            calls.append((command, env))
            (Path(env["PLAYWRIGHT_BROWSERS_PATH"]) / "chromium-1223").mkdir(parents=True)

        with tempfile.TemporaryDirectory() as tmp:
            manager = ChaoxingChromiumManager(
                root_dir=Path(tmp),
                progress_tracker=InMemoryProgressTracker(),
                command_runner=fake_runner,
                run_in_background=False,
            )

            status = manager.start_download()

            self.assertEqual(status.key, "chaoxing-chromium")
            self.assertEqual(len(calls), 1)
            command, env = calls[0]
            self.assertEqual(command[-4:], ["playwright", "install", "chromium", "--no-shell"])
            self.assertEqual(env["PLAYWRIGHT_BROWSERS_PATH"], str(Path(tmp) / "data" / "playwright-browsers"))
            self.assertTrue(manager.get_status().downloaded)
            self.assertEqual(manager.get_status().status, "completed")

    def test_run_command_includes_playwright_output_when_install_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Playwright Chromium 下载命令失败"):
            _run_command(["python", "-c", "import sys; print('download failed'); sys.exit(7)"], os.environ.copy())


if __name__ == "__main__":
    unittest.main()
