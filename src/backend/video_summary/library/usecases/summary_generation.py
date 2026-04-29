from __future__ import annotations

from backend.video_summary.library.models import VideoSummaryDTO
from backend.video_summary.library.ports import (
    VideoGenerationProgressTracker,
    VideoSummaryGenerator,
    VideoWorkspace,
)


class GenerateVideoSummaryFromLibrary:
    def __init__(
        self,
        workspace: VideoWorkspace,
        generator: VideoSummaryGenerator,
        progress_tracker: VideoGenerationProgressTracker,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._progress_tracker = progress_tracker

    async def run(
        self,
        series_id: str,
        video_id: str,
        transcript_enhancement_enabled: bool | None = None,
    ) -> VideoSummaryDTO | None:
        reporter = self._progress_tracker.create_reporter(f"{series_id}/{video_id}")
        try:
            await self._generator.run(
                series_id=series_id,
                video_id=video_id,
                progress_reporter=reporter,
                transcript_enhancement_enabled=transcript_enhancement_enabled,
            )
            reporter.completed("AI 概况已生成")
            return self._workspace.get_video_summary(series_id, video_id)
        except LookupError:
            return None
        except RuntimeError as error:
            reporter.failed(str(error))
            raise
        except Exception as error:
            reporter.failed(str(error))
            raise RuntimeError(str(error)) from error
