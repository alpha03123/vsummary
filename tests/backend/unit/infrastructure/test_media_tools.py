from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor


class FfmpegMediaProcessorTests(unittest.TestCase):
    def test_extract_audio_disables_ffmpeg_stdin(self) -> None:
        popen_calls: list[dict[str, Any]] = []

        class FakeProcess:
            returncode = 0

            def wait(self) -> int:
                return self.returncode

        def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
            popen_calls.append({"command": command, "kwargs": kwargs})
            return FakeProcess()

        with patch("backend.video_summary.infrastructure.media_tools.subprocess.Popen", fake_popen):
            FfmpegMediaProcessor().extract_audio(Path("input.m4a"), Path("output.wav"))

        self.assertEqual(1, len(popen_calls))
        command = popen_calls[0]["command"]
        kwargs = popen_calls[0]["kwargs"]
        self.assertIn("-nostdin", command)
        self.assertLess(command.index("-nostdin"), command.index("-i"))
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
