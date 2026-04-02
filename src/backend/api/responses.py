from __future__ import annotations

from pydantic import BaseModel

from backend.video_summary.library.views import VideoCardView, VideoLibraryView, VideoWorkspaceToolsView, WorkspaceToolView


class HealthResponse(BaseModel):
    status: str


class VideoCardResponse(BaseModel):
    id: str
    title: str
    source_name: str
    processed: bool
    status: str

    @classmethod
    def from_view(cls, video: VideoCardView) -> "VideoCardResponse":
        return cls(
            id=video.id,
            title=video.title,
            source_name=video.source_name,
            processed=video.processed,
            status=video.status,
        )


class SeriesResponse(BaseModel):
    id: str
    title: str
    videos: list[VideoCardResponse]


class WorkspaceResponse(BaseModel):
    id: str
    title: str


class VideoLibraryResponse(BaseModel):
    workspace: WorkspaceResponse
    series: list[SeriesResponse]

    @classmethod
    def from_view(cls, library: VideoLibraryView) -> "VideoLibraryResponse":
        return cls(
            workspace=WorkspaceResponse(
                id=library.workspace.id,
                title=library.workspace.title,
            ),
            series=[
                SeriesResponse(
                    id=series.id,
                    title=series.title,
                    videos=[VideoCardResponse.from_view(video) for video in series.videos],
                )
                for series in library.series
            ],
        )


class WorkspaceToolResponse(BaseModel):
    id: str
    title: str
    available: bool
    generated: bool
    status: str
    preview_url: str | None = None

    @classmethod
    def from_view(cls, tool: WorkspaceToolView) -> "WorkspaceToolResponse":
        return cls(
            id=tool.id,
            title=tool.title,
            available=tool.available,
            generated=tool.generated,
            status=tool.status,
            preview_url=tool.preview_url,
        )


class VideoWorkspaceToolsResponse(BaseModel):
    series_id: str
    video_id: str
    overview: WorkspaceToolResponse
    mindmap: WorkspaceToolResponse
    preview: WorkspaceToolResponse
    ai_todo: str

    @classmethod
    def from_view(cls, tools: VideoWorkspaceToolsView) -> "VideoWorkspaceToolsResponse":
        return cls(
            series_id=tools.series_id,
            video_id=tools.video_id,
            overview=WorkspaceToolResponse.from_view(tools.overview),
            mindmap=WorkspaceToolResponse.from_view(tools.mindmap),
            preview=WorkspaceToolResponse.from_view(tools.preview),
            ai_todo=tools.ai_todo,
        )
