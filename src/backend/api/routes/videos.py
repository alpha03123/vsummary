from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.contracts import (
    CreateVideoNoteRequest,
    GenerateVideoSummaryRequest,
    UpdateVideoNoteRequest,
)
from backend.api.responses import (
    SeriesResponse,
    VideoCardResponse,
    VideoChapterCardsResponse,
    VideoKnowledgeCardsResponse,
    VideoLibraryResponse,
    VideoNoteResponse,
    VideoNotesResponse,
    VideoWorkspaceToolsResponse,
)
from backend.api.sse import stream_progress_events
from backend.video_summary.infrastructure.runtime import AsrModelNotReadyError

router = APIRouter()


@router.get("/api/videos", response_model=VideoLibraryResponse)
def list_videos(container: ApiContainerDep) -> VideoLibraryResponse:
    library = container.list_video_library.run()
    return VideoLibraryResponse.from_model(library)


@router.get("/api/videos/{series_id}/{video_id}/summary")
def get_video_summary(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    _ensure_video_exists(container, series_id, video_id)
    video_summary = container.get_video_summary.run(series_id, video_id)
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return video_summary.summary


@router.get("/api/videos/{series_id}/{video_id}/mindmap")
def get_video_mindmap(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    _ensure_video_exists(container, series_id, video_id)
    video_mindmap = container.get_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"mindmap not found for video '{series_id}/{video_id}'")
    return video_mindmap.mindmap


@router.get("/api/videos/{series_id}/{video_id}/cards", response_model=VideoChapterCardsResponse)
def get_video_cards(series_id: str, video_id: str, container: ApiContainerDep) -> VideoChapterCardsResponse:
    _ensure_video_exists(container, series_id, video_id)
    video_cards = container.get_video_chapter_cards.run(series_id, video_id)
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"cards not found for video '{series_id}/{video_id}'")
    return VideoChapterCardsResponse.from_model(video_cards)


@router.get("/api/videos/{series_id}/{video_id}/knowledge-cards", response_model=VideoKnowledgeCardsResponse)
def get_video_knowledge_cards(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> VideoKnowledgeCardsResponse:
    _ensure_video_exists(container, series_id, video_id)
    video_cards = container.get_video_cards.run(series_id, video_id)
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"knowledge cards not found for video '{series_id}/{video_id}'")
    return VideoKnowledgeCardsResponse.from_model(video_cards)


@router.post("/api/videos/{series_id}/{video_id}/knowledge-cards/generate", response_model=VideoKnowledgeCardsResponse)
def generate_video_knowledge_cards(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> VideoKnowledgeCardsResponse:
    _ensure_video_exists(container, series_id, video_id)
    try:
        video_cards = container.generate_video_cards.run(series_id, video_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return VideoKnowledgeCardsResponse.from_model(video_cards)


@router.get("/api/videos/{series_id}/{video_id}/notes", response_model=VideoNotesResponse)
def get_video_notes(series_id: str, video_id: str, container: ApiContainerDep) -> VideoNotesResponse:
    video_notes = container.get_video_notes.run(series_id, video_id)
    if video_notes is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return VideoNotesResponse.from_model(video_notes)


@router.post("/api/videos/{series_id}/{video_id}/notes", response_model=VideoNoteResponse)
def create_video_note(
    series_id: str,
    video_id: str,
    request: CreateVideoNoteRequest,
    container: ApiContainerDep,
) -> VideoNoteResponse:
    try:
        note = container.create_video_note.run(
            series_id,
            video_id,
            title=request.title,
            content=request.content,
            source=request.source,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if note is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return VideoNoteResponse.from_model(note)


@router.put("/api/videos/{series_id}/{video_id}/notes/{note_id}", response_model=VideoNoteResponse)
def update_video_note(
    series_id: str,
    video_id: str,
    note_id: str,
    request: UpdateVideoNoteRequest,
    container: ApiContainerDep,
) -> VideoNoteResponse:
    try:
        note = container.update_video_note.run(
            series_id,
            video_id,
            note_id,
            title=request.title,
            content=request.content,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if container.get_video_source.run(series_id, video_id) is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    if note is None:
        raise HTTPException(status_code=404, detail=f"note not found '{note_id}'")
    return VideoNoteResponse.from_model(note)


@router.delete("/api/videos/{series_id}/{video_id}/notes/{note_id}")
def delete_video_note(
    series_id: str,
    video_id: str,
    note_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    deleted = container.delete_video_note.run(series_id, video_id, note_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    if deleted is False:
        raise HTTPException(status_code=404, detail=f"note not found '{note_id}'")
    return {"status": "deleted", "note_id": note_id}


@router.get("/api/videos/{series_id}/{video_id}/tools", response_model=VideoWorkspaceToolsResponse)
def get_video_tools(series_id: str, video_id: str, container: ApiContainerDep) -> VideoWorkspaceToolsResponse:
    video_tools = container.get_video_workspace_tools.run(series_id, video_id)
    if video_tools is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return VideoWorkspaceToolsResponse.from_model(video_tools)


@router.get("/api/videos/{series_id}/{video_id}/preview")
def preview_video(series_id: str, video_id: str, container: ApiContainerDep) -> FileResponse:
    source = container.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return FileResponse(source.source_path)


@router.post("/api/videos/{series_id}/{video_id}/generate")
async def generate_video_summary(
    series_id: str,
    video_id: str,
    request: GenerateVideoSummaryRequest | None = None,
    container: ApiContainerDep = None,
) -> dict[str, object]:
    try:
        video_summary = await container.generate_video_summary.run(
            series_id,
            video_id,
            transcript_enhancement_enabled=(
                None if request is None else request.transcript_enhancement_enabled
            ),
        )
    except AsrModelNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return video_summary.summary


@router.post("/api/videos/{series_id}/{video_id}/generate/cancel")
def cancel_video_summary_generation(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    container.generation_progress_tracker.request_cancel(_build_task_id(series_id, video_id))
    return {"status": "cancelled", "task_id": _build_task_id(series_id, video_id)}


@router.post("/api/series/{series_id}/generate")
async def generate_series_summaries(
    series_id: str,
    request: GenerateVideoSummaryRequest | None = None,
    container: ApiContainerDep = None,
) -> dict[str, object]:
    try:
        result = await container.generate_series_summaries.run(
            series_id,
            transcript_enhancement_enabled=(None if request is None else request.transcript_enhancement_enabled),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "series_id": result.series_id,
        "completed_videos": result.completed_videos,
        "skipped_videos": result.skipped_videos,
        "cancelled_video_id": result.cancelled_video_id,
    }


@router.post("/api/series/{series_id}/generate/cancel")
def cancel_series_summaries_generation(
    series_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    container.generation_progress_tracker.request_cancel(_build_series_task_id(series_id))
    return {"status": "cancelled", "task_id": _build_series_task_id(series_id)}


@router.post("/api/videos/{series_id}/{video_id}/mindmap/generate")
async def generate_video_mindmap(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    video_mindmap = await container.generate_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return video_mindmap.mindmap


@router.delete("/api/series/{series_id}")
def delete_series(series_id: str, container: ApiContainerDep) -> dict[str, object]:
    try:
        deleted = container.delete_series.run(series_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "series_id": deleted.series_id}


@router.delete("/api/videos/{series_id}/{video_id}")
def delete_video_source(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    try:
        deleted = container.delete_video_source.run(series_id, video_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "series_id": deleted.series_id, "video_id": deleted.video_id}


@router.post("/api/import/local/series", response_model=SeriesResponse)
async def import_local_series(
    series_title: str = Form(...),
    files: list[UploadFile] = File(...),
    container: ApiContainerDep = None,
) -> SeriesResponse:
    try:
        series = container.import_local_series.run(
            title=series_title,
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return SeriesResponse.from_model(series)


@router.post("/api/import/local/playground", response_model=list[VideoCardResponse])
async def import_local_playground_videos(
    files: list[UploadFile] = File(...),
    container: ApiContainerDep = None,
) -> list[VideoCardResponse]:
    try:
        videos = container.import_local_playground_videos.run(
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return [VideoCardResponse.from_model(video) for video in videos]


@router.post("/api/import/local/series/{series_id}", response_model=list[VideoCardResponse])
async def import_local_series_videos(
    series_id: str,
    files: list[UploadFile] = File(...),
    container: ApiContainerDep = None,
) -> list[VideoCardResponse]:
    try:
        videos = container.import_local_series_videos.run(
            series_id=series_id,
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return [VideoCardResponse.from_model(video) for video in videos]


@router.get("/api/videos/{series_id}/{video_id}/generate/progress")
async def stream_video_generation_progress(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    task_id = _build_task_id(series_id, video_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.generation_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/series/{series_id}/generate/progress")
async def stream_series_generation_progress(
    series_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    task_id = _build_series_task_id(series_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.generation_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _build_task_id(series_id: str, video_id: str) -> str:
    return f"{series_id}/{video_id}"


def _build_series_task_id(series_id: str) -> str:
    return f"series/{series_id}"


def _ensure_video_exists(container, series_id: str, video_id: str) -> None:
    if container.get_video_source.run(series_id, video_id) is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
