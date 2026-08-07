from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from backend.video_summary.infrastructure.asr.whisper_cpp_models import WhisperCppModelManager
from backend.video_summary.infrastructure.asr.whisper_cpp_transcriber import WhisperCppTranscriber


def test_whisper_cpp_model_manager_recognizes_manually_placed_ggml_model(tmp_path: Path) -> None:
    manager = WhisperCppModelManager(tmp_path / "data" / "models" / "whisper-cpp")
    model_path = manager.resolve_model_path("large-v3-turbo-q5_0")
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"ggml")

    assert manager.is_downloaded("large-v3-turbo-q5_0")


def test_whisper_cpp_transcriber_parses_cli_json(tmp_path: Path) -> None:
    binary = tmp_path / "whisper-cli"
    binary.write_text("", encoding="utf-8")
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"ggml")
    output_stem = tmp_path / "output" / "transcript"

    def fake_run(command, **kwargs):
        del kwargs
        output_base = Path(command[command.index("-of") + 1])
        Path(f"{output_base}.json").write_text(
            json.dumps(
                {
                    "result": {"language": "zh"},
                    "transcription": [
                        {"offsets": {"from": 1200, "to": 3400}, "text": "  测试文本  "},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, "", "")

    transcriber = WhisperCppTranscriber(binary_path=str(binary), model_path=model)
    with patch("backend.video_summary.infrastructure.asr.whisper_cpp_transcriber.subprocess.run", fake_run):
        transcript = transcriber.transcribe(tmp_path / "audio.wav", output_stem)

    assert transcript.language == "zh"
    assert transcript.segments[0].start_seconds == 1.2
    assert transcript.segments[0].end_seconds == 3.4
    assert transcript.full_text == "测试文本"
