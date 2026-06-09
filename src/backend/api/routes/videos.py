from __future__ import annotations

import asyncio
import logging
import json
import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.contracts import (
    CancelSeriesSummariesRequest,
    CreateVideoNoteRequest,
    GenerateSeriesSummariesRequest,
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
from backend.bilibili.ytdlp_bilibili import build_video_download_task_id
from backend.video_summary.infrastructure.video_summary_runtime import AsrModelNotReadyError
from backend.video_summary.generation.usecases.generate_summary import GenerateCancelledError
from backend.video_summary.library.markdown_exports import render_knowledge_cards_markdown
from backend.video_summary.library.markdown_exports import render_mixed_overview_markdown
from backend.video_summary.library.markdown_exports import render_notes_markdown
from backend.video_summary.library.markdown_exports import render_transcript_markdown
from backend.video_summary.library.usecases.mutations import GenerationInProgressError
from backend.video_summary.library.usecases.summary_generation import DuplicateSeriesGenerationError
from backend.video_summary.library.usecases.summary_generation import GenerationScopeBusyError

router = APIRouter()
LOGGER = logging.getLogger(__name__)


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


@router.get("/api/videos/{series_id}/{video_id}/exports/summary.md")
def export_video_summary_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> FileResponse:
    source = _ensure_video_exists(container, series_id, video_id)
    summary_path = source.output_dir / "summary.md"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail=f"summary markdown not found for video '{series_id}/{video_id}'")
    return FileResponse(
        summary_path,
        media_type="text/markdown; charset=utf-8",
        filename=_export_filename(video_id, "summary"),
    )


@router.get("/api/videos/{series_id}/{video_id}/exports/video")
def export_video_source(series_id: str, video_id: str, container: ApiContainerDep) -> FileResponse:
    source = _ensure_video_exists(container, series_id, video_id)
    media_type, _ = mimetypes.guess_type(source.source_path.name)
    return FileResponse(
        source.source_path,
        media_type=media_type or "application/octet-stream",
        filename=_video_export_filename(video_id, source.source_path.suffix),
    )


@router.get("/api/videos/{series_id}/{video_id}/exports/transcript.md")
def export_video_transcript_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    source = _ensure_video_exists(container, series_id, video_id)
    transcript_path = source.output_dir / "transcript.cleaned.json"
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    markdown = render_transcript_markdown(json.loads(transcript_path.read_text(encoding="utf-8")))
    return _markdown_response(markdown, _export_filename(video_id, "transcript"))


@router.get("/api/videos/{series_id}/{video_id}/exports/mixed.md")
def export_video_mixed_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    source = _ensure_video_exists(container, series_id, video_id)
    summary_path = source.output_dir / "summary.json"
    transcript_path = source.output_dir / "transcript.cleaned.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail=f"transcript not found for video '{series_id}/{video_id}'")
    markdown = render_mixed_overview_markdown(
        json.loads(summary_path.read_text(encoding="utf-8")),
        json.loads(transcript_path.read_text(encoding="utf-8")),
    )
    return _markdown_response(markdown, _export_filename(video_id, "mixed"))


@router.get("/api/videos/{series_id}/{video_id}/exports/knowledge-cards.md")
def export_video_knowledge_cards_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    source = _ensure_video_exists(container, series_id, video_id)
    cards_path = source.output_dir / "knowledge_cards.json"
    if not cards_path.exists():
        raise HTTPException(status_code=404, detail=f"knowledge cards not found for video '{series_id}/{video_id}'")
    markdown = render_knowledge_cards_markdown(json.loads(cards_path.read_text(encoding="utf-8")))
    return _markdown_response(markdown, _export_filename(video_id, "knowledge-cards"))


@router.get("/api/videos/{series_id}/{video_id}/exports/notes.md")
def export_video_notes_markdown(series_id: str, video_id: str, container: ApiContainerDep) -> Response:
    source = _ensure_video_exists(container, series_id, video_id)
    notes_path = source.output_dir / "notes.json"
    if not notes_path.exists():
        raise HTTPException(status_code=404, detail=f"notes not found for video '{series_id}/{video_id}'")
    payload = json.loads(notes_path.read_text(encoding="utf-8"))
    notes = payload.get("notes")
    if not isinstance(notes, list) or not notes:
        raise HTTPException(status_code=404, detail=f"notes not found for video '{series_id}/{video_id}'")
    markdown = render_notes_markdown(source.title, payload)
    return _markdown_response(markdown, _export_filename(video_id, "notes"))


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
    except GenerateCancelledError as error:
        raise HTTPException(status_code=409, detail="generation cancelled") from error
    except GenerationScopeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if video_summary is None:
        snapshot = container.generation_progress_tracker.get_snapshot(_build_task_id(series_id, video_id))
        if snapshot.status == "cancelled":
            raise HTTPException(status_code=409, detail="generation cancelled")
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
    request: GenerateSeriesSummariesRequest | None = None,
    container: ApiContainerDep = None,
) -> dict[str, object]:
    try:
        result = await container.generate_series_summaries.run(
            series_id,
            transcript_enhancement_enabled=(None if request is None else request.transcript_enhancement_enabled),
            run_id=(None if request is None else request.run_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except DuplicateSeriesGenerationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except GenerationScopeBusyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "series_id": result.series_id,
        "completed_videos": result.completed_videos,
        "skipped_videos": result.skipped_videos,
        "cancelled_videos": result.cancelled_videos,
        "cancelled_video_id": result.cancelled_video_id,
    }


@router.post("/api/series/{series_id}/generate/cancel")
def cancel_series_summaries_generation(
    series_id: str,
    container: ApiContainerDep,
    request: CancelSeriesSummariesRequest | None = None,
) -> dict[str, object]:
    series_task_id = _build_series_task_id(series_id)
    requested_run_id = None if request is None else request.run_id
    get_active_run_id = getattr(container.generate_series_summaries, "get_active_run_id", None)
    active_run_id = get_active_run_id(series_id) if callable(get_active_run_id) else None
    if requested_run_id is not None and active_run_id is not None and requested_run_id != active_run_id:
        LOGGER.info(
            "Ignoring stale series cancel: series_id=%s requested_run_id=%s active_run_id=%s",
            series_id,
            requested_run_id,
            active_run_id,
        )
        return {
            "status": "stale",
            "task_id": series_task_id,
            "active_run_id": active_run_id,
            "cancelled_video_ids": [],
        }
    container.generation_progress_tracker.request_cancel(series_task_id)
    pending_videos = _get_pending_series_videos(container, series_id)
    active_video_ids = container.generate_series_summaries.get_active_video_ids(series_id)
    linked_video_ids = {video.id for video in pending_videos if video.is_linked or video.status == "linked"}
    cancelled_video_ids = list(dict.fromkeys([*active_video_ids, *linked_video_ids]))
    LOGGER.info(
        "Cancelling series generation: series_id=%s requested_run_id=%s active_run_id=%s "
        "pending_video_ids=%s active_video_ids=%s linked_video_ids=%s cancelled_video_ids=%s",
        series_id,
        requested_run_id,
        active_run_id,
        [video.id for video in pending_videos],
        active_video_ids,
        sorted(linked_video_ids),
        cancelled_video_ids,
    )
    for video_id in active_video_ids:
        container.generation_progress_tracker.request_cancel(_build_task_id(series_id, video_id))
    for video_id in linked_video_ids:
        container.video_download_progress_tracker.request_cancel(build_video_download_task_id(series_id, video_id))
    if not active_video_ids:
        container.generation_progress_tracker.create_reporter(series_task_id).cancelled("任务已取消")
    return {
        "status": "cancelled",
        "task_id": series_task_id,
        "cancelled_video_ids": cancelled_video_ids,
    }


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
    except GenerationInProgressError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "series_id": deleted.series_id}


@router.delete("/api/videos/{series_id}/{video_id}")
def delete_video_source(series_id: str, video_id: str, container: ApiContainerDep) -> dict[str, object]:
    try:
        deleted = container.delete_video_source.run(series_id, video_id)
    except GenerationInProgressError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
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


@router.get("/api/videos/{series_id}/{video_id}/generate/status")
def get_video_generation_status(
    series_id: str,
    video_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    task_id = _build_task_id(series_id, video_id)
    return {
        "task_id": task_id,
        "snapshot": container.generation_progress_tracker.get_snapshot(task_id).to_dict(),
    }


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


@router.get("/api/series/{series_id}/generate/status")
def get_series_generation_status(
    series_id: str,
    container: ApiContainerDep,
) -> dict[str, object]:
    task_id = _build_series_task_id(series_id)
    return {
        "task_id": task_id,
        "snapshot": container.generation_progress_tracker.get_snapshot(task_id).to_dict(),
    }


def _build_task_id(series_id: str, video_id: str) -> str:
    return f"{series_id}/{video_id}"


def _build_series_task_id(series_id: str) -> str:
    return f"series/{series_id}"


def _get_pending_series_videos(container, series_id: str) -> list[object]:
    library = container.list_video_library.run()
    series = next((item for item in library.series if item.id == series_id), None)
    if series is None:
        raise HTTPException(status_code=404, detail=f"series not found '{series_id}'")
    return [video for video in series.videos if not video.processed]


def _ensure_video_exists(container, series_id: str, video_id: str):
    source = container.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    return source


def _markdown_response(markdown: str, filename: str) -> Response:
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_attachment(filename)},
    )


def _content_disposition_attachment(filename: str) -> str:
    ascii_filename = filename.encode("ascii", errors="ignore").decode("ascii") or "export.md"
    quoted_filename = ascii_filename.replace("\\", "\\\\").replace('"', r"\"")
    encoded_filename = quote(filename, safe="")
    return f'attachment; filename="{quoted_filename}"; filename*=UTF-8\'\'{encoded_filename}'


def _export_filename(video_id: str, export_name: str) -> str:
    return f"{_safe_filename_part(video_id)}-{export_name}.md"


def _video_export_filename(video_id: str, suffix: str) -> str:
    return f"{_safe_filename_part(video_id)}{suffix}"


def _safe_filename_part(value: str) -> str:
    result = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_"}:
            result.append(char)
        else:
            result.append("-")
    return "".join(result).strip("-") or "video"
