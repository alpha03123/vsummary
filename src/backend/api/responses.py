from __future__ import annotations

from pydantic import BaseModel

from backend.video_summary.library.views import VideoCardView, VideoLibraryView


class HealthResponse(BaseModel):
    status: str


class VideoCardResponse(BaseModel):
    id: str
    title: str

    @classmethod
    def from_view(cls, video: VideoCardView) -> "VideoCardResponse":
        return cls(id=video.id, title=video.title)


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
    videos: list[VideoCardResponse]

    @classmethod
    def from_view(cls, library: VideoLibraryView) -> "VideoLibraryResponse":
        videos = [VideoCardResponse.from_view(video) for video in library.videos]
        return cls(
            workspace=WorkspaceResponse(
                id=library.workspace.id,
                title=library.workspace.title,
            ),
            series=[
                SeriesResponse(
                    id=library.series.id,
                    title=library.series.title,
                    videos=videos,
                )
            ],
            videos=videos,
        )
