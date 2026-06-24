from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


from backend.video_summary.infrastructure.asr.faster_whisper_transcriber import (
    FasterWhisperTranscriber,
    _discover_nvidia_bin_dirs,
)


class FasterWhisperTranscriberTests(unittest.TestCase):
    def test_cpu_transcriber_does_not_require_nvidia_packages(self) -> None:
        fake_module = types.ModuleType("faster_whisper")
        fake_module.WhisperModel = FakeWhisperModel
        previous_module = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = fake_module
        try:
            with patch(
                "backend.video_summary.infrastructure.asr.faster_whisper_transcriber._ensure_windows_cuda_dll_dirs",
                side_effect=AssertionError("CPU mode must not scan CUDA DLL dirs"),
            ):
                transcriber = FasterWhisperTranscriber(
                    "model-dir",
                    device="cpu",
                    compute_type="int8",
                    transcription_mode="fast",
                )
        finally:
            if previous_module is None:
                sys.modules.pop("faster_whisper", None)
            else:
                sys.modules["faster_whisper"] = previous_module

        self.assertIsInstance(transcriber, FasterWhisperTranscriber)

    def test_missing_nvidia_namespace_is_ignored_when_discovering_cuda_dlls(self) -> None:
        with patch(
            "backend.video_summary.infrastructure.asr.faster_whisper_transcriber.importlib.util.find_spec",
            side_effect=ModuleNotFoundError("No module named 'nvidia'"),
        ):
            self.assertEqual(_discover_nvidia_bin_dirs(), [])


class FakeWhisperModel:
    def __init__(self, model_size: str, *, device: str, compute_type: str) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
