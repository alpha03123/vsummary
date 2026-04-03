from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse

from backend.api.bootstrap import build_api_container
from backend.api.responses import (
    HealthResponse,
    VideoLibraryResponse,
    VideoWorkspaceToolsResponse,
)
from backend.video_summary.infrastructure.settings import (
    WorkspaceUiSettings,
    load_settings,
    replace_faster_whisper_model_size,
    replace_workspace_ui_settings,
    save_settings,
)

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = build_api_container(ROOT)

app = FastAPI(title="video_include api")


class GenerateVideoSummaryRequest(BaseModel):
    transcript_enhancement_enabled: bool | None = None


class WorkspaceSettingsResponse(BaseModel):
    theme: str
    show_takeaways: bool
    ai_transcript_enhancement: bool
    asr_model_quality: str


class UpdateWorkspaceSettingsRequest(BaseModel):
    theme: str
    show_takeaways: bool
    ai_transcript_enhancement: bool
    asr_model_quality: str


class FasterWhisperModelResponse(BaseModel):
    id: str
    label: str
    downloaded: bool
    current: bool
    recommended: bool


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/videos", response_model=VideoLibraryResponse)
def list_videos() -> VideoLibraryResponse:
    library = CONTAINER.list_video_library.run()
    return VideoLibraryResponse.from_view(library)


@app.get("/api/settings", response_model=WorkspaceSettingsResponse)
def get_workspace_settings() -> WorkspaceSettingsResponse:
    settings = load_settings(CONTAINER.config_path, CONTAINER.root_dir)
    return WorkspaceSettingsResponse(
        theme=settings.workspace_ui.theme,
        show_takeaways=settings.workspace_ui.show_takeaways,
        ai_transcript_enhancement=settings.workspace_ui.ai_transcript_enhancement,
        asr_model_quality=settings.asr.faster_whisper.model_size,
    )


@app.put("/api/settings", response_model=WorkspaceSettingsResponse)
def update_workspace_settings(request: UpdateWorkspaceSettingsRequest) -> WorkspaceSettingsResponse:
    if request.theme not in {"light", "dark"}:
        raise HTTPException(status_code=400, detail=f"unsupported theme '{request.theme}'")
    if not CONTAINER.faster_whisper_model_manager.is_supported(request.asr_model_quality):
        raise HTTPException(status_code=400, detail=f"unsupported asr model '{request.asr_model_quality}'")

    current_settings = load_settings(CONTAINER.config_path, CONTAINER.root_dir)
    next_workspace_ui = WorkspaceUiSettings(
        theme=request.theme,
        show_takeaways=request.show_takeaways,
        ai_transcript_enhancement=request.ai_transcript_enhancement,
    )
    next_settings = replace_workspace_ui_settings(current_settings, next_workspace_ui)
    next_settings = replace_faster_whisper_model_size(next_settings, request.asr_model_quality)
    save_settings(CONTAINER.config_path, next_settings)
    return WorkspaceSettingsResponse(
        theme=next_workspace_ui.theme,
        show_takeaways=next_workspace_ui.show_takeaways,
        ai_transcript_enhancement=next_workspace_ui.ai_transcript_enhancement,
        asr_model_quality=request.asr_model_quality,
    )


@app.get("/api/asr/faster-whisper/models", response_model=list[FasterWhisperModelResponse])
def list_faster_whisper_models() -> list[FasterWhisperModelResponse]:
    settings = load_settings(CONTAINER.config_path, CONTAINER.root_dir)
    return [
        FasterWhisperModelResponse(
            id=model.id,
            label=model.label,
            downloaded=model.downloaded,
            current=model.current,
            recommended=model.recommended,
        )
        for model in CONTAINER.faster_whisper_model_manager.list_models(settings.asr.faster_whisper.model_size)
    ]


@app.post("/api/asr/faster-whisper/models/{model_id}/download", response_model=FasterWhisperModelResponse)
def download_faster_whisper_model(model_id: str) -> FasterWhisperModelResponse:
    if not CONTAINER.faster_whisper_model_manager.is_supported(model_id):
        raise HTTPException(status_code=400, detail=f"unsupported faster-whisper model '{model_id}'")

    CONTAINER.faster_whisper_model_manager.download(model_id)
    settings = load_settings(CONTAINER.config_path, CONTAINER.root_dir)
    downloaded_model = next(
        model
        for model in CONTAINER.faster_whisper_model_manager.list_models(settings.asr.faster_whisper.model_size)
        if model.id == model_id
    )
    return FasterWhisperModelResponse(
        id=downloaded_model.id,
        label=downloaded_model.label,
        downloaded=downloaded_model.downloaded,
        current=downloaded_model.current,
        recommended=downloaded_model.recommended,
    )


@app.get("/api/videos/{series_id}/{video_id}/summary")
def get_video_summary(series_id: str, video_id: str) -> dict[str, object]:
    video_summary = CONTAINER.get_video_summary.run(series_id, video_id)
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")

    return video_summary.summary


@app.get("/api/videos/{series_id}/{video_id}/mindmap")
def get_video_mindmap(series_id: str, video_id: str) -> dict[str, object]:
    video_mindmap = CONTAINER.get_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"mindmap not found for video '{series_id}/{video_id}'")

    return video_mindmap.mindmap


@app.get("/api/videos/{series_id}/{video_id}/tools", response_model=VideoWorkspaceToolsResponse)
def get_video_tools(series_id: str, video_id: str) -> VideoWorkspaceToolsResponse:
    video_tools = CONTAINER.get_video_workspace_tools.run(series_id, video_id)
    if video_tools is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")

    return VideoWorkspaceToolsResponse.from_view(video_tools)


@app.get("/api/videos/{series_id}/{video_id}/preview")
def preview_video(series_id: str, video_id: str) -> FileResponse:
    source = CONTAINER.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")

    return FileResponse(source.source_path)


@app.post("/api/videos/{series_id}/{video_id}/generate")
def generate_video_summary(
    series_id: str,
    video_id: str,
    request: GenerateVideoSummaryRequest | None = None,
) -> dict[str, object]:
    video_summary = CONTAINER.generate_video_summary.run(
        series_id,
        video_id,
        transcript_enhancement_enabled=(
            None if request is None else request.transcript_enhancement_enabled
        ),
    )
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")

    return video_summary.summary


@app.post("/api/videos/{series_id}/{video_id}/mindmap/generate")
def generate_video_mindmap(series_id: str, video_id: str) -> dict[str, object]:
    video_mindmap = CONTAINER.generate_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")

    return video_mindmap.mindmap


@app.get("/api/videos/{series_id}/{video_id}/generate/progress")
async def stream_video_generation_progress(series_id: str, video_id: str) -> StreamingResponse:
    task_id = _build_task_id(series_id, video_id)

    async def event_stream():
        last_sequence = -1
        while True:
            snapshot = CONTAINER.generation_progress_tracker.get_snapshot(task_id)
            if snapshot.sequence != last_sequence:
                last_sequence = snapshot.sequence
                yield f"data: {json.dumps(snapshot.to_dict(), ensure_ascii=False)}\n\n"
            if snapshot.status in {"completed", "failed"}:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _build_task_id(series_id: str, video_id: str) -> str:
    return f"{series_id}/{video_id}"
