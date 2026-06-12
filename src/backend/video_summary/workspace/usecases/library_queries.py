from __future__ import annotations

from backend.video_summary.workspace.models import (
    VideoChapterCardsDTO,
    VideoKnowledgeCardsDTO,
    VideoLibraryDTO,
    VideoMindmapDTO,
    VideoSourceDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
    VideoWorkspaceToolsDTO,
)
from backend.video_summary.workspace.ports import VideoLibraryReader


class ListVideoLibrary:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self) -> VideoLibraryDTO:
        return VideoLibraryDTO(workspace=self._workspace.get_workspace(), series=self._workspace.list_series())


class GetVideoSummary:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        return self._workspace.get_video_summary(series_id, video_id)


class GetVideoSource:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        return self._workspace.get_video_source(series_id, video_id)


class GetVideoTranscript:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        return self._workspace.get_video_transcript(series_id, video_id)


class GetVideoMindmap:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        return self._workspace.get_video_mindmap(series_id, video_id)


class GetVideoChapterCards:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        return self._workspace.get_video_chapter_cards(series_id, video_id)


class GetVideoKnowledgeCards:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        return self._workspace.get_video_knowledge_cards(series_id, video_id)


class GetVideoWorkspaceTools:
    def __init__(self, workspace: VideoLibraryReader) -> None:
        self._workspace = workspace

    def run(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        return self._workspace.get_video_workspace_tools(series_id, video_id)
