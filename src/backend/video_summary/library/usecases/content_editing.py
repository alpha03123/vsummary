"""人工修订视频总结和转写的用例。"""

from __future__ import annotations

from backend.video_summary.library.models import VideoSummaryDTO, VideoTranscriptDTO
from backend.video_summary.library.ports import VideoContentEditor, WorkspaceIndexRefresher
from backend.video_summary.library.usecases.series_synopsis_generation import RefreshSeriesKnowledgeMemory


class UpdateVideoSummary:
    """保存人工修订后的总结，并刷新其派生索引。"""

    def __init__(
        self,
        workspace: VideoContentEditor,
        series_memory_refresher: RefreshSeriesKnowledgeMemory,
    ) -> None:
        self._workspace = workspace
        self._series_memory_refresher = series_memory_refresher

    def run(self, series_id: str, video_id: str, *, markdown: str) -> VideoSummaryDTO | None:
        result = self._workspace.update_video_summary(series_id, video_id, markdown=markdown)
        if result is not None:
            self._series_memory_refresher.refresh(series_id, video_id)
        return result


class UpdateVideoTranscript:
    """保存人工修订后的转写，并刷新 RAG 索引。"""

    def __init__(self, workspace: VideoContentEditor, index_refresher: WorkspaceIndexRefresher) -> None:
        self._workspace = workspace
        self._index_refresher = index_refresher

    def run(
        self,
        series_id: str,
        video_id: str,
        *,
        markdown: str,
    ) -> VideoTranscriptDTO | None:
        result = self._workspace.update_video_transcript(series_id, video_id, markdown=markdown)
        if result is not None:
            self._index_refresher.upsert_video(series_id, video_id)
        return result
