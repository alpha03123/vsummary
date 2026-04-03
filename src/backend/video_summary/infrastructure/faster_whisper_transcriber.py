from __future__ import annotations

from pathlib import Path
from typing import Callable

from backend.video_summary.domain.models import Transcript, TranscriptSegment


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_size: str,
        device: str,
        compute_type: str,
        language: str = "zh",
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError("faster-whisper is not installed.") from error

        resolved_device = _resolve_device(device)
        self._language = language
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
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
            temperature=0.0,
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
    if device == "gpu":
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
