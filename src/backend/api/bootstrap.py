from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.ports import VideoSummaryGenerator
from backend.video_summary.library.usecases.browse_library import (
    GenerateVideoSummaryFromLibrary,
    GetVideoSummary,
    ListVideoLibrary,
)


@dataclass(frozen=True)
class ApiContainer:
    list_video_library: ListVideoLibrary
    get_video_summary: GetVideoSummary
    generate_video_summary: GenerateVideoSummaryFromLibrary


def build_api_container(root_dir: Path, generator: VideoSummaryGenerator | None = None) -> ApiContainer:
    workspace = FileSystemVideoWorkspace(root_dir)
    resolved_generator = generator or ConfiguredVideoSummaryWorkflow(root_dir)
    return ApiContainer(
        list_video_library=ListVideoLibrary(workspace),
        get_video_summary=GetVideoSummary(workspace),
        generate_video_summary=GenerateVideoSummaryFromLibrary(workspace, resolved_generator),
    )
