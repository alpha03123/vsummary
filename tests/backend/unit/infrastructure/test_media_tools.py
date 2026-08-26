from __future__ import annotations

import subprocess
import tempfile
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

    def test_ensure_browser_playable_mp4_skips_faststart_media(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "faststart.mp4"
            video_path.write_bytes(_mp4(b"ftyp", b"moov", b"mdat"))

            with patch("backend.video_summary.infrastructure.media_tools.subprocess.run") as run:
                result = FfmpegMediaProcessor().ensure_browser_playable_mp4(video_path)

        self.assertEqual(video_path, result)
        run.assert_not_called()

    def test_ensure_browser_playable_mp4_remuxes_tail_index_media(self) -> None:
        run_calls: list[list[str]] = []

        def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
            del kwargs
            run_calls.append(command)
            Path(command[-1]).write_bytes(_mp4(b"ftyp", b"moov", b"mdat"))
            return SimpleNamespace(returncode=0, stderr=b"")

        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "tail-index.mp4"
            video_path.write_bytes(_mp4(b"ftyp", b"mdat", b"moov"))

            with patch("backend.video_summary.infrastructure.media_tools.subprocess.run", fake_run):
                result = FfmpegMediaProcessor().ensure_browser_playable_mp4(video_path)

            self.assertEqual(video_path, result)
            self.assertEqual(_mp4(b"ftyp", b"moov", b"mdat"), video_path.read_bytes())

        command = run_calls[0]
        self.assertEqual("copy", command[command.index("-c") + 1])
        self.assertEqual("+faststart", command[command.index("-movflags") + 1])


def _mp4(*box_types: bytes) -> bytes:
    return b"".join((8).to_bytes(4, "big") + box_type for box_type in box_types)


if __name__ == "__main__":
    unittest.main()
