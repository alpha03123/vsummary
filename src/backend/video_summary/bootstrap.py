from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.generation.usecases.generate_summary import GenerateVideoSummary
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from backend.video_summary.infrastructure.runtime import (
    VideoSummaryRuntime,
    build_video_summary_runtime,
)
from backend.video_summary.infrastructure.settings import AppSettings, load_settings


@dataclass(frozen=True)
class VideoSummaryApplication:
    settings: AppSettings
    runtime: VideoSummaryRuntime
    use_case: GenerateVideoSummary


def load_video_summary_application(
    config_path: Path,
    root_dir: Path,
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> VideoSummaryApplication:
    settings = load_settings(config_path=config_path, root_dir=root_dir)
    runtime = build_video_summary_runtime(
        settings,
        model=model,
        base_url=base_url,
    )
    use_case = GenerateVideoSummary(
        media_processor=FfmpegMediaProcessor(),
        transcriber=runtime.transcriber,
        summarizer=runtime.summarizer,
    )
    return VideoSummaryApplication(
        settings=settings,
        runtime=runtime,
        use_case=use_case,
    )
