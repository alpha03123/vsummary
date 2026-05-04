from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.faster_whisper_transcriber import FasterWhisperTranscriber
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.infrastructure.litellm_summarizer import LiteLLMCompletionSummarizer
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
    gateway: LiteLLMCompletionGateway
    asr: AsrRuntimeInfo


class AsrModelNotReadyError(RuntimeError):
    pass


def build_litellm_completion_gateway(settings: AppSettings) -> LiteLLMCompletionGateway:
    return LiteLLMCompletionGateway(
        provider=settings.openai.provider,
        model=settings.openai.model,
        base_url=settings.openai.base_url,
        api_key=settings.openai.api_key,
    )


def build_video_summary_runtime(
    settings: AppSettings,
) -> VideoSummaryRuntime:
    transcriber, asr = _build_transcriber(settings)
    gateway = build_litellm_completion_gateway(settings)
    summarizer = LiteLLMCompletionSummarizer(
        gateway=gateway,
        context_window_tokens=settings.agent_context.window_tokens,
        reserved_output_tokens=settings.agent_context.reserved_output_tokens,
        direct_summary_threshold_ratio=settings.agent_context.direct_summary_threshold_ratio,
        summary_chunk_concurrency=settings.generation.summary_chunk_concurrency,
    )
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
        if not model_manager.is_downloaded(settings.asr.faster_whisper.model_size):
            raise AsrModelNotReadyError(
                "当前语音模型尚未下载，请先到设置中下载后再生成 AI 概况。"
            )
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
