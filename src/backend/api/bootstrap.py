from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.faster_whisper_models import FasterWhisperModelManager
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
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
    config_path: Path
    root_dir: Path
    faster_whisper_model_manager: FasterWhisperModelManager
    list_video_library: ListVideoLibrary
    get_video_source: GetVideoSource
    get_video_summary: GetVideoSummary
    get_video_mindmap: GetVideoMindmap
    get_video_workspace_tools: GetVideoWorkspaceTools
    generate_video_summary: GenerateVideoSummaryFromLibrary
    generate_video_mindmap: GenerateVideoMindmapFromLibrary
    generation_progress_tracker: InMemoryProgressTracker


def build_api_container(
    root_dir: Path,
    generator: VideoSummaryGenerator | None = None,
    mindmap_generator: VideoMindmapGenerator | None = None,
    faster_whisper_model_manager: FasterWhisperModelManager | None = None,
) -> ApiContainer:
    config_path = root_dir / "config" / "settings.toml"
    workspace = FileSystemVideoWorkspace(root_dir)
    progress_tracker = InMemoryProgressTracker()
    model_manager = faster_whisper_model_manager or FasterWhisperModelManager(
        root_dir / "data" / "models" / "faster-whisper"
    )
    resolved_generator = generator or ConfiguredVideoSummaryWorkflow(root_dir)
    resolved_mindmap_generator = mindmap_generator or ConfiguredMindmapWorkflow(root_dir)
    return ApiContainer(
        config_path=config_path,
        root_dir=root_dir,
        faster_whisper_model_manager=model_manager,
        list_video_library=ListVideoLibrary(workspace),
        get_video_source=GetVideoSource(workspace),
        get_video_summary=GetVideoSummary(workspace),
        get_video_mindmap=GetVideoMindmap(workspace),
        get_video_workspace_tools=GetVideoWorkspaceTools(workspace),
        generate_video_summary=GenerateVideoSummaryFromLibrary(workspace, resolved_generator, progress_tracker),
        generate_video_mindmap=GenerateVideoMindmapFromLibrary(workspace, resolved_mindmap_generator),
        generation_progress_tracker=progress_tracker,
    )
