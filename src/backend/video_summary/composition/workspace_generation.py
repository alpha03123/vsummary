from __future__ import annotations

from backend.video_summary.summary_generation.ports import ProgressReporter
from backend.video_summary.composition.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.composition.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.summary_generation.service_ports import VideoMindmapGenerator, VideoSummaryGenerator
from backend.video_summary.workspace.ports import VideoLibraryReader


class WorkspaceBackedVideoSummaryGenerator(VideoSummaryGenerator):
    def __init__(self, workspace: VideoLibraryReader, workflow: ConfiguredVideoSummaryWorkflow) -> None:
        self._workspace = workspace
        self._workflow = workflow

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        video = _require_video_source(self._workspace, series_id, video_id)
        await self._workflow.run(
            video.source_path,
            video.output_dir,
            progress_reporter=progress_reporter,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
        )


class WorkspaceBackedVideoMindmapGenerator(VideoMindmapGenerator):
    def __init__(self, workspace: VideoLibraryReader, workflow: ConfiguredMindmapWorkflow) -> None:
        self._workspace = workspace
        self._workflow = workflow

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        summary_data: dict[str, object],
    ) -> None:
        video = _require_video_source(self._workspace, series_id, video_id)
        await self._workflow.run(video.source_path, video.output_dir, summary_data)


def _require_video_source(workspace: VideoLibraryReader, series_id: str, video_id: str):
    video = workspace.get_video_source(series_id, video_id)
    if video is None:
        raise LookupError(f"video not found '{series_id}/{video_id}'")
    return video
