from __future__ import annotations

from pydantic import BaseModel

from backend.video_summary.library.views import VideoCardView, VideoLibraryView


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
