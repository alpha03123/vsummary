from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.library.ports import VideoMindmapGenerator, VideoSummaryGenerator
from backend.video_summary.library.usecases.browse_library import (
    GenerateVideoMindmapFromLibrary,
    GenerateVideoSummaryFromLibrary,
    GetVideoMindmap,
    GetVideoSource,
    GetVideoSummary,
    GetVideoWorkspaceTools,
    ListVideoLibrary,
)


@dataclass(frozen=True)
class ApiContainer:
    list_video_library: ListVideoLibrary
    get_video_source: GetVideoSource
    get_video_summary: GetVideoSummary
    get_video_mindmap: GetVideoMindmap
    get_video_workspace_tools: GetVideoWorkspaceTools
    generate_video_summary: GenerateVideoSummaryFromLibrary
    generate_video_mindmap: GenerateVideoMindmapFromLibrary


def build_api_container(
    root_dir: Path,
    generator: VideoSummaryGenerator | None = None,
    mindmap_generator: VideoMindmapGenerator | None = None,
) -> ApiContainer:
    workspace = FileSystemVideoWorkspace(root_dir)
    resolved_generator = generator or ConfiguredVideoSummaryWorkflow(root_dir)
    resolved_mindmap_generator = mindmap_generator or ConfiguredMindmapWorkflow(root_dir)
    return ApiContainer(
        list_video_library=ListVideoLibrary(workspace),
        get_video_source=GetVideoSource(workspace),
        get_video_summary=GetVideoSummary(workspace),
        get_video_mindmap=GetVideoMindmap(workspace),
        get_video_workspace_tools=GetVideoWorkspaceTools(workspace),
        generate_video_summary=GenerateVideoSummaryFromLibrary(workspace, resolved_generator),
        generate_video_mindmap=GenerateVideoMindmapFromLibrary(workspace, resolved_mindmap_generator),
    )
