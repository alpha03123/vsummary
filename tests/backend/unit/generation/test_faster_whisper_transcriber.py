from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_transcriber_passes_initial_prompt_to_faster_whisper(self) -> None:
        fake_module = types.ModuleType("faster_whisper")
        fake_module.WhisperModel = FakeWhisperModel
        previous_module = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = fake_module
        try:
            transcriber = FasterWhisperTranscriber(
                "model-dir",
                device="cpu",
                compute_type="int8",
                transcription_mode="fast",
                initial_prompt="以下为简体中文普通话转写文本。",
            )
            with patch.object(
                transcriber._model,
                "transcribe",
                return_value=(iter([]), SimpleNamespace(duration=0, language="zh")),
            ) as transcribe:
                transcriber.transcribe(Path("audio.wav"), Path("transcript"))
        finally:
            if previous_module is None:
                sys.modules.pop("faster_whisper", None)
            else:
                sys.modules["faster_whisper"] = previous_module

        self.assertEqual(transcribe.call_args.kwargs["initial_prompt"], "以下为简体中文普通话转写文本。")
        self.assertIn("以下为简体中文普通话转写文本。", transcriber.cache_identity)

    def test_auto_language_simplifies_chinese_transcript(self) -> None:
        transcriber = self._build_transcriber()
        with patch.object(
            transcriber._model,
            "transcribe",
            return_value=(
                iter([SimpleNamespace(start=0.0, end=1.0, text="繁體中文")]),
                SimpleNamespace(duration=1.0, language="zh"),
            ),
        ) as transcribe, patch(
            "backend.video_summary.infrastructure.asr.faster_whisper_transcriber._load_chinese_simplifier",
            return_value=lambda text: text.replace("繁體", "繁体"),
        ) as simplify_chinese:
            transcript = transcriber.transcribe(Path("audio.wav"), Path("transcript"))

        self.assertEqual(transcribe.call_args.kwargs["language"], None)
        self.assertEqual(transcript.language, "zh")
        self.assertEqual(transcript.full_text, "繁体中文")
        simplify_chinese.assert_called_once_with()

    def test_auto_language_does_not_normalize_english_transcript(self) -> None:
        transcriber = self._build_transcriber()
        with patch.object(
            transcriber._model,
            "transcribe",
            return_value=(
                iter([SimpleNamespace(start=0.0, end=1.0, text="English transcript")]),
                SimpleNamespace(duration=1.0, language="en"),
            ),
        ) as transcribe, patch(
            "backend.video_summary.infrastructure.asr.faster_whisper_transcriber._load_chinese_simplifier",
            side_effect=AssertionError("English transcript must not use OpenCC"),
        ):
            transcript = transcriber.transcribe(Path("audio.wav"), Path("transcript"))

        self.assertEqual(transcribe.call_args.kwargs["language"], None)
        self.assertEqual(transcript.language, "en")
        self.assertEqual(transcript.full_text, "English transcript")

    def _build_transcriber(self) -> FasterWhisperTranscriber:
        fake_module = types.ModuleType("faster_whisper")
        fake_module.WhisperModel = FakeWhisperModel
        previous_module = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = fake_module
        self.addCleanup(_restore_module, "faster_whisper", previous_module)
        return FasterWhisperTranscriber(
            "model-dir",
            device="cpu",
            compute_type="int8",
            transcription_mode="fast",
        )


class FakeWhisperModel:
    def __init__(self, model_size: str, *, device: str, compute_type: str) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, audio_path: str, **kwargs):
        del audio_path, kwargs
        raise AssertionError("transcribe must be patched in this test")


def _restore_module(name: str, previous_module: types.ModuleType | None) -> None:
    if previous_module is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = previous_module
