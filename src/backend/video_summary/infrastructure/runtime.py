from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.faster_whisper_transcriber import FasterWhisperTranscriber
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.openai_summary import OpenAICompletionGateway
from backend.video_summary.infrastructure.openai_summarizer import OpenAICompletionSummarizer
from backend.video_summary.infrastructure.settings import AppSettings
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
    gateway: OpenAICompletionGateway
    asr: AsrRuntimeInfo


def build_openai_completion_gateway(settings: AppSettings) -> OpenAICompletionGateway:
    return OpenAICompletionGateway(
        model=settings.openai.model,
        base_url=settings.openai.base_url,
        api_key=settings.openai.api_key,
    )


def build_video_summary_runtime(
    settings: AppSettings,
) -> VideoSummaryRuntime:
    transcriber, asr = _build_transcriber(settings)
    gateway = build_openai_completion_gateway(settings)
    summarizer = OpenAICompletionSummarizer(gateway=gateway)
    return VideoSummaryRuntime(
        transcriber=transcriber,
        summarizer=summarizer,
        gateway=gateway,
        asr=asr,
    )


def _build_transcriber(settings: AppSettings) -> tuple[Transcriber, AsrRuntimeInfo]:
    provider = settings.asr.provider
    if provider == "faster_whisper":
        model_manager = FasterWhisperModelManager(settings.asr.faster_whisper.models_dir)
        return (
            FasterWhisperTranscriber(
                model_size=model_manager.resolve_model_source(settings.asr.faster_whisper.model_size),
                device=settings.asr.faster_whisper.device,
                compute_type=settings.asr.faster_whisper.compute_type,
                transcription_mode=settings.asr.faster_whisper.transcription_mode,
                language=settings.asr.language,
            ),
            AsrRuntimeInfo(
                provider=provider,
                device=settings.asr.faster_whisper.device,
                model_label=settings.asr.faster_whisper.model_size,
            ),
        )

    raise ValueError(f"Unsupported ASR provider: {provider}")
