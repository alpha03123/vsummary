"""视频总结子运行时的依赖装配（顶层容器）。

业务目的：把 `AppSettings` 翻译成"视频总结流程需要的全部实例"：
- ASR 转写器（当前仅 `faster_whisper`）；
- LiteLLM 网关；
- 上层总结器；
- 运行时元信息（用于诊断/UI 展示）。

入口：
- `build_video_summary_runtime(settings)` 一次性产出 `VideoSummaryRuntime`
  不可变容器供上层注入；
- `build_litellm_completion_gateway(settings)` 在只想要网关时单独调用
  （如 `LiteLLMTranscriptEnhancer` 复用）。
未下载 ASR 模型时抛 `AsrModelNotReadyError`，引导用户去设置页下载。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.asr.faster_whisper_transcriber import FasterWhisperTranscriber
from backend.video_summary.infrastructure.asr.faster_whisper_models import FasterWhisperModelManager
from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.infrastructure.llm.litellm_summarizer import LiteLLMCompletionSummarizer
from backend.video_summary.infrastructure.config.settings import AppSettings
from backend.video_summary.generation.ports import Summarizer, Transcriber


@dataclass(frozen=True)
class AsrRuntimeInfo:
    """ASR 运行时元信息（用于日志/前端展示）。

    业务目的：把"当前选中的 provider / 设备 / 模型"以可读字段的形式透出，
    供诊断、设置页与前端头部展示；`executable_path` 暂为预留。
    """

    provider: str
    device: str
    model_label: str
    executable_path: Path | None = None


@dataclass(frozen=True)
class VideoSummaryRuntime:
    """视频总结子运行时的不可变容器。

    业务目的：把"一次生成所需的全部实例"打包成一个值对象，让上层容器
    只需注入一次即可获得转写器、总结器、LLM 网关与 ASR 元信息。

    Attributes:
        transcriber: 已加载的 ASR 转写器实现（满足 `Transcriber` Port）。
        summarizer: 已注入 LiteLLM 网关的总结器实现（满足 `Summarizer` Port）。
        gateway: LiteLLM 网关实例，可被 `LiteLLMTranscriptEnhancer` 等其他组件复用。
        asr: ASR 运行时元信息。
    """

    transcriber: Transcriber
    summarizer: Summarizer
    gateway: LiteLLMCompletionGateway
    asr: AsrRuntimeInfo


class AsrModelNotReadyError(RuntimeError):
    """当前 faster-whisper 模型尚未下载，无法构建转写器时抛出。

    业务目的：把"模型未下载"这种前置条件错误与 `ValueError` 等参数错误
    区分开，供上层引导用户去设置页下载模型。
    """


def build_litellm_completion_gateway(settings: AppSettings) -> LiteLLMCompletionGateway:
    """根据 settings 构建 `LiteLLMCompletionGateway`。

    `reasoning_effort` 取自 `settings.agent_context.reasoning_effort`，便于把
    Agent 层的"是否启用深度思考"与总结流程保持一致。
    """
    return LiteLLMCompletionGateway(
        provider=settings.openai.provider,
        model=settings.openai.model,
        base_url=settings.openai.base_url,
        api_key=settings.openai.api_key,
        reasoning_effort=settings.agent_context.reasoning_effort,
    )


def build_video_summary_runtime(
    settings: AppSettings,
) -> VideoSummaryRuntime:
    """根据 settings 装配完整的视频总结运行时。

    Args:
        settings: 已加载的应用配置。

    Returns:
        包含转写器、总结器、LLM 网关、ASR 元信息的 `VideoSummaryRuntime`。

    Raises:
        AsrModelNotReadyError: 选定的 faster-whisper 模型尚未下载。
        ValueError: 选定的 ASR provider 不受支持。
    """
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
    """根据 `settings.asr.provider` 分发到对应的转写器实现。

    当前仅支持 `faster_whisper`：会先校验模型是否已下载，未下载则抛出
    `AsrModelNotReadyError` 以便上层引导用户去设置页下载。
    """
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
