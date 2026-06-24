"""视频总结与思维导图用例的依赖注入工厂集合。

本模块负责把配置 (`AppSettings`)、底层适配器（ffmpeg、LiteLLM 转写增强器、
总结器、思维导图生成器）和文件制品存储"装配"成上层用例可直接使用的对象，
是 `infrastructure` 层对外暴露的两个最常用入口。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.generation.usecases.generate_mindmap import GenerateMindmap
from backend.video_summary.generation.usecases.generate_summary import GenerateVideoSummary
from backend.video_summary.infrastructure.storage.filesystem_generation_artifact_store import FileSystemGenerationArtifactStore
from backend.video_summary.infrastructure.llm.litellm_mindmap_generator import LiteLLMMindmapGenerator
from backend.video_summary.infrastructure.llm.litellm_transcript_enhancer import LiteLLMTranscriptEnhancer
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from backend.video_summary.infrastructure.video_summary_runtime import (
    build_litellm_completion_gateway,
    build_video_summary_runtime,
)
from backend.video_summary.infrastructure.config.settings import AppSettings, load_settings


@dataclass(frozen=True)
class VideoSummaryApplication:
    """视频总结用例与其对应配置的不可变组合。

    Attributes:
        settings: 当前生效的 `AppSettings`，调用方可在启动时读取用于诊断/展示。
        use_case: 已注入好全部依赖的 `GenerateVideoSummary` 用例。
    """

    settings: AppSettings
    use_case: GenerateVideoSummary


@dataclass(frozen=True)
class MindmapApplication:
    """思维导图用例与其对应配置的不可变组合。

    Attributes:
        settings: 当前生效的 `AppSettings`。
        use_case: 已注入好生成器与制品存储的 `GenerateMindmap` 用例。
    """

    settings: AppSettings
    use_case: GenerateMindmap


def build_video_summary_application(
    config_path: Path,
    root_dir: Path,
    transcript_enhancement_enabled: bool | None = None,
) -> VideoSummaryApplication:
    """装配单视频总结用例及其全部依赖。

    装配步骤：
        1. 从 `config_path` 加载 `AppSettings`；
        2. 用 settings 构建 LiteLLM 网关、ASR 转写器、总结器等子运行时；
        3. 根据 `transcript_enhancement_enabled`（`None` 时使用 settings 默认值）
           决定是否装配 `LiteLLMTranscriptEnhancer`；
        4. 注入文件制品存储 + ffmpeg 媒体处理器，得到 `GenerateVideoSummary` 用例。

    Args:
        config_path: settings.toml 配置文件路径。
        root_dir: 项目根目录，用于解析模型缓存等相对路径。
        transcript_enhancement_enabled: 显式覆盖"是否启用转写增强"；为 `None`
            时读 `settings.asr.transcript_enhancement_enabled`。

    Returns:
        包含 settings 与组装好用例的 `VideoSummaryApplication`。
    """
    settings = load_settings(config_path=config_path, root_dir=root_dir)
    resolved_transcript_enhancement_enabled = (
        settings.asr.transcript_enhancement_enabled
        if transcript_enhancement_enabled is None
        else transcript_enhancement_enabled
    )
    runtime = build_video_summary_runtime(settings)
    artifact_store = FileSystemGenerationArtifactStore()
    use_case = GenerateVideoSummary(
        media_processor=FfmpegMediaProcessor(),
        transcriber=runtime.transcriber,
        transcript_enhancer=(
            LiteLLMTranscriptEnhancer(gateway=runtime.gateway)
            if resolved_transcript_enhancement_enabled
            else None
        ),
        summarizer=runtime.summarizer,
        artifact_store=artifact_store,
    )
    return VideoSummaryApplication(settings=settings, use_case=use_case)


def build_mindmap_application(config_path: Path, root_dir: Path) -> MindmapApplication:
    """装配思维导图用例及其全部依赖。

    Args:
        config_path: settings.toml 配置文件路径。
        root_dir: 项目根目录，用于解析模型缓存等相对路径。

    Returns:
        包含 settings 与 `GenerateMindmap` 用例的 `MindmapApplication`。
    """
    settings = load_settings(config_path=config_path, root_dir=root_dir)
    gateway = build_litellm_completion_gateway(settings)
    use_case = GenerateMindmap(
        generator=LiteLLMMindmapGenerator(gateway=gateway),
        artifact_store=FileSystemGenerationArtifactStore(),
    )
    return MindmapApplication(settings=settings, use_case=use_case)


def build_series_mindmap_application(config_path: Path, root_dir: Path) -> MindmapApplication:
    """装配系列思维导图用例及其全部依赖。

    Args:
        config_path: settings.toml 配置文件路径。
        root_dir: 项目根目录，用于解析模型缓存等相对路径。

    Returns:
        包含 settings 与 `GenerateSeriesMindmap` 用例的 `MindmapApplication`。
    """
    from backend.video_summary.generation.usecases.generate_series_mindmap import GenerateSeriesMindmap
    from backend.video_summary.infrastructure.llm.litellm_series_mindmap_generator import LiteLLMSeriesMindmapGenerator

    settings = load_settings(config_path=config_path, root_dir=root_dir)
    gateway = build_litellm_completion_gateway(settings)
    use_case = GenerateSeriesMindmap(
        generator=LiteLLMSeriesMindmapGenerator(gateway=gateway),
        artifact_store=FileSystemGenerationArtifactStore(),
    )
    return MindmapApplication(settings=settings, use_case=use_case)
