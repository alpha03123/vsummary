from __future__ import annotations

import json
import subprocess
from pathlib import Path

from domain.models import Transcript, TranscriptSegment
from infra.settings import WhisperCppSettings


def resolve_whisper_executable(settings: WhisperCppSettings) -> Path:
    device = settings.device
    cpu_executable = settings.runtime_paths.cpu_executable
    gpu_executable = settings.runtime_paths.gpu_executable

    if device == "cpu":
        _require_file(cpu_executable, "CPU runtime")
        return cpu_executable

    if device == "gpu":
        _require_file(gpu_executable, "GPU runtime")
        _require_nvidia_smi()
        return gpu_executable

    if _is_nvidia_gpu_available() and gpu_executable.exists():
        return gpu_executable

    _require_file(cpu_executable, "CPU runtime")
    return cpu_executable


def _is_nvidia_gpu_available() -> bool:
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return "NVIDIA-SMI" in result.stdout


def _require_nvidia_smi() -> None:
    if not _is_nvidia_gpu_available():
        raise RuntimeError("GPU mode requested, but NVIDIA runtime is not available.")


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


class WhisperCppTranscriber:
    def __init__(self, executable_path: Path, model_path: Path, language: str = "zh") -> None:
        self._executable_path = executable_path
        self._model_path = model_path
        self._language = language

    def transcribe(self, audio_path: Path, output_stem: Path) -> Transcript:
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                str(self._executable_path),
                "-m",
                str(self._model_path),
                "-f",
                str(audio_path),
                "-l",
                self._language,
                "-ojf",
                "-of",
                str(output_stem),
                "-np",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        json_path = output_stem.with_suffix(".json")
        payload = json.loads(json_path.read_bytes().decode("utf-8", errors="replace"))
        raw_segments = payload.get("transcription", [])
        segments = [
            TranscriptSegment(
                start_seconds=float(segment["offsets"]["from"]) / 1000.0,
                end_seconds=float(segment["offsets"]["to"]) / 1000.0,
                text=segment["text"].strip(),
            )
            for segment in raw_segments
            if segment.get("text", "").strip()
        ]
        language = payload.get("result", {}).get("language", self._language)
        return Transcript(language=language, segments=segments)
