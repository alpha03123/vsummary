from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from backend.video_summary.generation.ports import NoTranscribableAudioError
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor


class FfmpegMediaProcessorTests(unittest.TestCase):
    def test_extract_audio_disables_ffmpeg_stdin(self) -> None:
        popen_calls: list[dict[str, Any]] = []

        class FakeProcess:
            returncode = 0

            def wait(self) -> int:
                return self.returncode

            def communicate(self) -> tuple[None, bytes]:
                return None, b""

        def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
            popen_calls.append({"command": command, "kwargs": kwargs})
            return FakeProcess()

        with (
            patch(
                "backend.video_summary.infrastructure.media_tools.subprocess.run",
                return_value=SimpleNamespace(stdout="0\n"),
            ),
            patch("backend.video_summary.infrastructure.media_tools.subprocess.Popen", fake_popen),
        ):
            FfmpegMediaProcessor().extract_audio(Path("input.m4a"), Path("output.wav"))

        self.assertEqual(1, len(popen_calls))
        command = popen_calls[0]["command"]
        kwargs = popen_calls[0]["kwargs"]
        self.assertIn("-nostdin", command)
        self.assertLess(command.index("-nostdin"), command.index("-i"))
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.PIPE)

    def test_extract_frame_preserves_ffmpeg_stderr_and_logs_raw_failure(self) -> None:
        popen_calls: list[dict[str, Any]] = []

        class FakeProcess:
            returncode = -22

            def communicate(self) -> tuple[None, bytes]:
                return None, b"Invalid duration for option ss: nan"

        def fake_popen(command: list[str], **kwargs: Any) -> FakeProcess:
            popen_calls.append({"command": command, "kwargs": kwargs})
            return FakeProcess()

        with (
            patch(
                "backend.video_summary.infrastructure.media_tools.subprocess.run",
                return_value=SimpleNamespace(stdout="0\n"),
            ),
            patch("backend.video_summary.infrastructure.media_tools.subprocess.Popen", fake_popen),
            patch("backend.video_summary.infrastructure.media_tools.LOGGER.exception") as log_exception,
        ):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                FfmpegMediaProcessor().extract_frame(Path("input.mp4"), 12.5, Path("chapter.jpg"))

        self.assertEqual(raised.exception.returncode, -22)
        self.assertEqual(raised.exception.stderr, b"Invalid duration for option ss: nan")
        command = popen_calls[0]["command"]
        self.assertEqual(command[command.index("-ss") + 1], "12.500")
        self.assertIn("-update", command)
        self.assertIs(popen_calls[0]["kwargs"]["stderr"], subprocess.PIPE)
        self.assertEqual(log_exception.call_args.kwargs["extra"]["stderr"], "Invalid duration for option ss: nan")

    def test_extract_audio_reports_missing_audio_stream_without_running_ffmpeg(self) -> None:
        with (
            patch(
                "backend.video_summary.infrastructure.media_tools.subprocess.run",
                return_value=SimpleNamespace(stdout=""),
            ),
            patch("backend.video_summary.infrastructure.media_tools.subprocess.Popen") as popen,
        ):
            with self.assertRaises(NoTranscribableAudioError):
                FfmpegMediaProcessor().extract_audio(Path("silent.mp4"), Path("output.wav"))

        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
