from pathlib import Path
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

from backend.local.desktop_media_picker import select_local_media_paths


class MacMediaPickerTests(unittest.TestCase):
    def test_returns_multiple_unicode_paths_without_loading_tk(self):
        folder = Path('/tmp/媒体 "files"')
        with patch("backend.local.desktop_media_picker.sys.platform", "darwin"), patch(
            "backend.local.desktop_media_picker.subprocess.run",
            return_value=CompletedProcess([], 0, "/tmp/中文 one.mp4\n/tmp/two.wav\n", ""),
        ) as run:
            paths = select_local_media_paths(initial_directory=folder)
        self.assertEqual(paths, ["/tmp/中文 one.mp4", "/tmp/two.wav"])
        # Paths are arguments, never interpolated into executable AppleScript.
        self.assertEqual(run.call_args.args[0][-2:], [str(folder), "true"])

    def test_cancel_is_an_empty_selection(self):
        with patch("backend.local.desktop_media_picker.sys.platform", "darwin"), patch(
            "backend.local.desktop_media_picker.subprocess.run", return_value=CompletedProcess([], 0, "\n", ""),
        ):
            self.assertEqual(select_local_media_paths(allow_multiple=False), [])

    def test_dialog_failure_is_reported(self):
        with patch("backend.local.desktop_media_picker.sys.platform", "darwin"), patch(
            "backend.local.desktop_media_picker.subprocess.run", return_value=CompletedProcess([], 1, "", "failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "macOS"):
                select_local_media_paths()
