from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.faster_whisper_transcriber import FasterWhisperTranscriber
from backend.video_summary.infrastructure.openai_summarizer import OpenAIResponsesClient
from backend.video_summary.infrastructure.sensevoice import SenseVoiceTranscriber
from backend.video_summary.infrastructure.settings import AppSettings
from backend.video_summary.infrastructure.whisper_cpp import (
    WhisperCppTranscriber,
    resolve_whisper_executable,
)
from backend.video_summary.generation.ports import Summarizer, Transcriber


@dataclass(frozen=True)
class AsrRuntimeInfo:
    provider: str
    device: str
    model_label: str
    executable_path: Path | None = None


@dataclass(frozen=True)
class VideoSummaryRuntime:
    transcriber: Transcriber
    summarizer: Summarizer
    asr: AsrRuntimeInfo
    model: str
    base_url: str


def build_video_summary_runtime(
    settings: AppSettings,
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> VideoSummaryRuntime:
    resolved_model = model or settings.openai.model
    resolved_base_url = base_url or settings.openai.base_url
    transcriber, asr = _build_transcriber(settings)
    summarizer = OpenAIResponsesClient(model=resolved_model, base_url=resolved_base_url)
    return VideoSummaryRuntime(
        transcriber=transcriber,
        summarizer=summarizer,
        asr=asr,
        model=resolved_model,
        base_url=resolved_base_url,
    )


def _build_transcriber(settings: AppSettings) -> tuple[Transcriber, AsrRuntimeInfo]:
    provider = settings.asr.provider
    if provider == "whisper_cpp":
        executable_path = resolve_whisper_executable(settings.asr.whisper_cpp)
        return (
            WhisperCppTranscriber(
                executable_path=executable_path,
                model_path=settings.asr.whisper_cpp.model_path,
                language=settings.asr.language,
            ),
            AsrRuntimeInfo(
                provider=provider,
                device=settings.asr.whisper_cpp.device,
                model_label=settings.asr.whisper_cpp.model_path.name,
                executable_path=executable_path,
            ),
        )

    if provider == "faster_whisper":
        return (
            FasterWhisperTranscriber(
                model_size=settings.asr.faster_whisper.model_size,
                device=settings.asr.faster_whisper.device,
                compute_type=settings.asr.faster_whisper.compute_type,
                language=settings.asr.language,
            ),
            AsrRuntimeInfo(
                provider=provider,
                device=settings.asr.faster_whisper.device,
                model_label=settings.asr.faster_whisper.model_size,
            ),
        )

    if provider == "sensevoice":
        return (
            SenseVoiceTranscriber(
                model_id=settings.asr.sensevoice.model_id,
                device=settings.asr.sensevoice.device,
            ),
            AsrRuntimeInfo(
                provider=provider,
                device=settings.asr.sensevoice.device,
                model_label=settings.asr.sensevoice.model_id,
            ),
        )

    raise ValueError(f"Unsupported ASR provider: {provider}")
