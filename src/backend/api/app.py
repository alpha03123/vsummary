from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from backend.api.bootstrap import build_api_container
from backend.api.responses import (
    HealthResponse,
    VideoLibraryResponse,
)

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = build_api_container(ROOT)

app = FastAPI(title="video_include api")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/videos", response_model=VideoLibraryResponse)
def list_videos() -> VideoLibraryResponse:
    library = CONTAINER.list_video_library.run()
    return VideoLibraryResponse.from_view(library)


@app.get("/api/videos/{video_id}/summary")
def get_video_summary(video_id: str) -> dict[str, object]:
    video_summary = CONTAINER.get_video_summary.run(video_id)
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{video_id}'")

    return video_summary.summary
