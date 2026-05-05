from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable

from backend.video_summary.domain.models import Transcript, TranscriptSegment

_CUDA_DLL_HANDLES: list[object] = []
_CUDA_DLL_DIRS_READY = False


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_size: str,
        device: str,
        compute_type: str,
        transcription_mode: str,
        language: str = "zh",
    ) -> None:
        resolved_device = _resolve_device(device)
        if resolved_device == "cuda":
            _ensure_windows_cuda_dll_dirs()

        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error

        self._language = language
        self._decode_options = _build_decode_options(transcription_mode)
        self._model = WhisperModel(
            model_size,
            device=resolved_device,
            compute_type=compute_type,
        )

    def transcribe(
        self,
        audio_path: Path,
        output_stem: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=self._language,
            vad_filter=True,
            **self._decode_options,
        )
        total_duration = getattr(info, "duration", None)
        segments = []
        for segment in segments_iter:
            if not segment.text.strip():
                continue
            segments.append(
                TranscriptSegment(
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=segment.text.strip(),
                ),
            )
            if on_progress is not None and total_duration:
                on_progress(float(segment.end) / float(total_duration))
        return Transcript(language=getattr(info, "language", self._language), segments=segments)


def _resolve_device(device: str) -> str:
    if device == "auto":
        return "cuda" if _is_nvidia_gpu_available() else "cpu"
    if device in {"gpu", "cuda"}:
        if not _is_nvidia_gpu_available():
            raise RuntimeError("GPU mode requested, but NVIDIA runtime is not available.")
        return "cuda"
    return "cpu"


def _is_nvidia_gpu_available() -> bool:
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return "NVIDIA-SMI" in result.stdout


def _ensure_windows_cuda_dll_dirs() -> None:
    global _CUDA_DLL_DIRS_READY

    if _CUDA_DLL_DIRS_READY or sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidates = _discover_nvidia_bin_dirs()

    existing_path_entries = os.environ.get("PATH", "").split(os.pathsep)
    prepended_entries: list[str] = []

    for path in candidates:
        if not path.exists():
            continue

        resolved = str(path)
        _CUDA_DLL_HANDLES.append(os.add_dll_directory(resolved))
        if resolved not in existing_path_entries and resolved not in prepended_entries:
            prepended_entries.append(resolved)

    if prepended_entries:
        os.environ["PATH"] = os.pathsep.join([*prepended_entries, *existing_path_entries])

    _CUDA_DLL_DIRS_READY = True


def _discover_nvidia_bin_dirs() -> list[Path]:
    package_names = (
        "nvidia.cublas",
        "nvidia.cudnn",
        "nvidia.cuda_nvrtc",
        "nvidia.cuda_runtime",
    )
    candidates: list[Path] = []
    for package_name in package_names:
        try:
            spec = importlib.util.find_spec(package_name)
        except ModuleNotFoundError:
            continue
        locations = getattr(spec, "submodule_search_locations", None)
        if not locations:
            continue
        for location in locations:
            bin_dir = Path(location) / "bin"
            if bin_dir.exists() and bin_dir not in candidates:
                candidates.append(bin_dir)
    return candidates


def _build_decode_options(transcription_mode: str) -> dict[str, object]:
    if transcription_mode == "accurate":
        return {
            "beam_size": 5,
            "best_of": 5,
            "condition_on_previous_text": True,
            "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        }
    if transcription_mode == "balanced":
        return {
            "beam_size": 3,
            "best_of": 3,
            "condition_on_previous_text": True,
            "temperature": 0.0,
        }
    return {
        "beam_size": 1,
        "best_of": 1,
        "condition_on_previous_text": False,
        "temperature": 0.0,
    }
