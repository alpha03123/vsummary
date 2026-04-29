from __future__ import annotations

import asyncio
import inspect
import json
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse

from backend.api.bootstrap import build_api_container
from backend.bilibili.download_starter import build_video_download_task_id
from backend.api.settings_service import ProviderSettingsUpdate, SettingsValidationError, WorkspaceSettingsUpdate
from backend.api.responses import (
    AgentChatRequest,
    AgentChatResponse,
    AgentContextUsageRequest,
    AgentContextUsageResponse,
    AgentSessionRecoveryRequest,
    AgentSessionRecoveryResponse,
    AgentSessionClearRequest,
    HealthResponse,
    LinkedVideoDownloadResponse,
    ResolveBilibiliSeriesRequest,
    ResolveBilibiliVideoRequest,
    SeriesResponse,
    VideoCardResponse,
    VideoChapterCardsResponse,
    VideoKnowledgeCardsResponse,
    VideoLibraryResponse,
    VideoNoteResponse,
    VideoNotesResponse,
    VideoWorkspaceToolsResponse,
)
from backend.agent.memory.context import AgentContext
from backend.video_summary.infrastructure.settings import (
    load_settings,
)
from backend.video_summary.infrastructure.runtime import AsrModelNotReadyError

ROOT = Path(__file__).resolve().parents[3]
CONTAINER = build_api_container(ROOT)
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="video_include api")


class GenerateVideoSummaryRequest(BaseModel):
    transcript_enhancement_enabled: bool | None = None


class CreateVideoNoteRequest(BaseModel):
    title: str
    content: str
    source: str = "manual"


class UpdateVideoNoteRequest(BaseModel):
    title: str
    content: str


class WorkspaceSettingsResponse(BaseModel):
    theme: str
    show_takeaways: bool
    transcript_enhancement_enabled: bool
    asr_model_quality: str
    transcription_mode: str


class UpdateWorkspaceSettingsRequest(BaseModel):
    theme: str
    show_takeaways: bool
    transcript_enhancement_enabled: bool
    asr_model_quality: str
    transcription_mode: str


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
    return VideoLibraryResponse.from_model(library)


@app.get("/api/settings", response_model=WorkspaceSettingsResponse)
def get_workspace_settings() -> WorkspaceSettingsResponse:
    settings = CONTAINER.settings_service.get_workspace_settings()
    return WorkspaceSettingsResponse(
        theme=settings.theme,
        show_takeaways=settings.show_takeaways,
        transcript_enhancement_enabled=settings.transcript_enhancement_enabled,
        asr_model_quality=settings.asr_model_quality,
        transcription_mode=settings.transcription_mode,
    )


@app.put("/api/settings", response_model=WorkspaceSettingsResponse)
def update_workspace_settings(request: UpdateWorkspaceSettingsRequest) -> WorkspaceSettingsResponse:
    try:
        settings = CONTAINER.settings_service.update_workspace_settings(
            WorkspaceSettingsUpdate(
                theme=request.theme,
                show_takeaways=request.show_takeaways,
                transcript_enhancement_enabled=request.transcript_enhancement_enabled,
                asr_model_quality=request.asr_model_quality,
                transcription_mode=request.transcription_mode,
            )
        )
    except SettingsValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return WorkspaceSettingsResponse(
        theme=settings.theme,
        show_takeaways=settings.show_takeaways,
        transcript_enhancement_enabled=settings.transcript_enhancement_enabled,
        asr_model_quality=settings.asr_model_quality,
        transcription_mode=settings.transcription_mode,
    )


class ProviderSettingsResponse(BaseModel):
    llm_provider: str
    openai_base_url: str
    openai_model: str
    has_openai_api_key: bool
    openai_api_key_masked: str


class UpdateProviderSettingsRequest(BaseModel):
    llm_provider: str
    openai_base_url: str
    openai_model: str
    openai_api_key: str | None = None


@app.get("/api/provider-settings", response_model=ProviderSettingsResponse)
def get_provider_settings() -> ProviderSettingsResponse:
    env_settings = CONTAINER.settings_service.get_provider_settings()
    return ProviderSettingsResponse(
        llm_provider=env_settings.llm_provider,
        openai_base_url=env_settings.openai_base_url,
        openai_model=env_settings.openai_model,
        has_openai_api_key=env_settings.has_openai_api_key,
        openai_api_key_masked=env_settings.openai_api_key_masked,
    )


@app.put("/api/provider-settings", response_model=ProviderSettingsResponse)
def update_provider_settings(request: UpdateProviderSettingsRequest) -> ProviderSettingsResponse:
    try:
        env_settings = CONTAINER.settings_service.update_provider_settings(
            ProviderSettingsUpdate(
                llm_provider=request.llm_provider,
                openai_base_url=request.openai_base_url,
                openai_model=request.openai_model,
                openai_api_key=request.openai_api_key,
            )
        )
    except SettingsValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ProviderSettingsResponse(
        llm_provider=env_settings.llm_provider,
        openai_base_url=env_settings.openai_base_url,
        openai_model=env_settings.openai_model,
        has_openai_api_key=env_settings.has_openai_api_key,
        openai_api_key_masked=env_settings.openai_api_key_masked,
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

    reporter = CONTAINER.model_download_progress_tracker.create_reporter(_build_model_download_task_id(model_id))
    try:
        CONTAINER.faster_whisper_model_manager.download(model_id, progress_reporter=reporter)
    except Exception as error:
        if "取消" in str(error):
            reporter.cancelled("模型下载已取消")
            raise HTTPException(status_code=409, detail="模型下载已取消") from error
        reporter.failed(str(error))
        raise
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


@app.get("/api/asr/faster-whisper/models/{model_id}/download/progress")
async def stream_faster_whisper_model_download_progress(model_id: str) -> StreamingResponse:
    task_id = _build_model_download_task_id(model_id)
    return StreamingResponse(
        _stream_progress_events(
            tracker=CONTAINER.model_download_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/asr/faster-whisper/models/{model_id}/download/cancel")
def cancel_faster_whisper_model_download(model_id: str) -> dict[str, object]:
    CONTAINER.model_download_progress_tracker.request_cancel(_build_model_download_task_id(model_id))
    return {"status": "cancelled"}


@app.get("/api/videos/{series_id}/{video_id}/summary")
def get_video_summary(series_id: str, video_id: str) -> dict[str, object]:
    _ensure_video_exists(series_id, video_id)
    video_summary = CONTAINER.get_video_summary.run(series_id, video_id)
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")

    return video_summary.summary


@app.get("/api/videos/{series_id}/{video_id}/mindmap")
def get_video_mindmap(series_id: str, video_id: str) -> dict[str, object]:
    _ensure_video_exists(series_id, video_id)
    video_mindmap = CONTAINER.get_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"mindmap not found for video '{series_id}/{video_id}'")

    return video_mindmap.mindmap


@app.get("/api/videos/{series_id}/{video_id}/cards", response_model=VideoChapterCardsResponse)
def get_video_cards(series_id: str, video_id: str) -> VideoChapterCardsResponse:
    _ensure_video_exists(series_id, video_id)
    video_cards = CONTAINER.get_video_chapter_cards.run(series_id, video_id)
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"cards not found for video '{series_id}/{video_id}'")

    return VideoChapterCardsResponse.from_model(video_cards)


@app.get("/api/videos/{series_id}/{video_id}/knowledge-cards", response_model=VideoKnowledgeCardsResponse)
def get_video_knowledge_cards(series_id: str, video_id: str) -> VideoKnowledgeCardsResponse:
    _ensure_video_exists(series_id, video_id)
    video_cards = CONTAINER.get_video_cards.run(series_id, video_id)
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"knowledge cards not found for video '{series_id}/{video_id}'")

    return VideoKnowledgeCardsResponse.from_model(video_cards)


@app.post("/api/videos/{series_id}/{video_id}/knowledge-cards/generate", response_model=VideoKnowledgeCardsResponse)
def generate_video_knowledge_cards(series_id: str, video_id: str) -> VideoKnowledgeCardsResponse:
    _ensure_video_exists(series_id, video_id)
    video_cards = CONTAINER.generate_video_cards.run(series_id, video_id)
    if video_cards is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")
    return VideoKnowledgeCardsResponse.from_model(video_cards)


@app.get("/api/videos/{series_id}/{video_id}/notes", response_model=VideoNotesResponse)
def get_video_notes(series_id: str, video_id: str) -> VideoNotesResponse:
    video_notes = CONTAINER.get_video_notes.run(series_id, video_id)
    if video_notes is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")

    return VideoNotesResponse.from_model(video_notes)


@app.post("/api/videos/{series_id}/{video_id}/notes", response_model=VideoNoteResponse)
def create_video_note(
    series_id: str,
    video_id: str,
    request: CreateVideoNoteRequest,
) -> VideoNoteResponse:
    try:
        note = CONTAINER.create_video_note.run(
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


@app.put("/api/videos/{series_id}/{video_id}/notes/{note_id}", response_model=VideoNoteResponse)
def update_video_note(
    series_id: str,
    video_id: str,
    note_id: str,
    request: UpdateVideoNoteRequest,
) -> VideoNoteResponse:
    try:
        note = CONTAINER.update_video_note.run(
            series_id,
            video_id,
            note_id,
            title=request.title,
            content=request.content,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if CONTAINER.get_video_source.run(series_id, video_id) is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    if note is None:
        raise HTTPException(status_code=404, detail=f"note not found '{note_id}'")
    return VideoNoteResponse.from_model(note)


@app.delete("/api/videos/{series_id}/{video_id}/notes/{note_id}")
def delete_video_note(series_id: str, video_id: str, note_id: str) -> dict[str, object]:
    deleted = CONTAINER.delete_video_note.run(series_id, video_id, note_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")
    if deleted is False:
        raise HTTPException(status_code=404, detail=f"note not found '{note_id}'")
    return {"status": "deleted", "note_id": note_id}


@app.get("/api/videos/{series_id}/{video_id}/tools", response_model=VideoWorkspaceToolsResponse)
def get_video_tools(series_id: str, video_id: str) -> VideoWorkspaceToolsResponse:
    video_tools = CONTAINER.get_video_workspace_tools.run(series_id, video_id)
    if video_tools is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")

    return VideoWorkspaceToolsResponse.from_model(video_tools)


@app.get("/api/videos/{series_id}/{video_id}/preview")
def preview_video(series_id: str, video_id: str) -> FileResponse:
    source = CONTAINER.get_video_source.run(series_id, video_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")

    return FileResponse(source.source_path)


@app.post("/api/videos/{series_id}/{video_id}/generate")
async def generate_video_summary(
    series_id: str,
    video_id: str,
    request: GenerateVideoSummaryRequest | None = None,
) -> dict[str, object]:
    try:
        video_summary = await CONTAINER.generate_video_summary.run(
            series_id,
            video_id,
            transcript_enhancement_enabled=(
                None if request is None else request.transcript_enhancement_enabled
            ),
        )
    except AsrModelNotReadyError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if video_summary is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")

    return video_summary.summary


@app.post("/api/videos/{series_id}/{video_id}/mindmap/generate")
async def generate_video_mindmap(series_id: str, video_id: str) -> dict[str, object]:
    video_mindmap = await CONTAINER.generate_video_mindmap.run(series_id, video_id)
    if video_mindmap is None:
        raise HTTPException(status_code=404, detail=f"summary not found for video '{series_id}/{video_id}'")

    return video_mindmap.mindmap


@app.delete("/api/series/{series_id}")
def delete_series(series_id: str) -> dict[str, object]:
    try:
        deleted = CONTAINER.delete_series.run(series_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "series_id": deleted.series_id}


@app.delete("/api/videos/{series_id}/{video_id}")
def delete_video_source(series_id: str, video_id: str) -> dict[str, object]:
    try:
        deleted = CONTAINER.delete_video_source.run(series_id, video_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"status": "deleted", "series_id": deleted.series_id, "video_id": deleted.video_id}


@app.post("/api/import/local/series", response_model=SeriesResponse)
async def import_local_series(
    series_title: str = Form(...),
    files: list[UploadFile] = File(...),
) -> SeriesResponse:
    try:
        series = CONTAINER.import_local_series.run(
            title=series_title,
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return SeriesResponse.from_model(series)


@app.post("/api/import/local/playground", response_model=list[VideoCardResponse])
async def import_local_playground_videos(files: list[UploadFile] = File(...)) -> list[VideoCardResponse]:
    try:
        videos = CONTAINER.import_local_playground_videos.run(
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return [VideoCardResponse.from_model(video) for video in videos]


@app.post("/api/import/local/series/{series_id}", response_model=list[VideoCardResponse])
async def import_local_series_videos(series_id: str, files: list[UploadFile] = File(...)) -> list[VideoCardResponse]:
    try:
        videos = CONTAINER.import_local_series_videos.run(
            series_id=series_id,
            files=[(file.filename or "", file.file) for file in files],
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await asyncio.gather(*(file.close() for file in files), return_exceptions=True)

    return [VideoCardResponse.from_model(video) for video in videos]


@app.post("/api/agent/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest) -> AgentChatResponse:
    context_override = _build_agent_context_override(request.session_id, request.context)

    try:
        result = CONTAINER.get_agent_service().run_turn(
            session_id=request.session_id,
            user_message=request.message,
            context_override=context_override,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return AgentChatResponse.from_result(result)


@app.post("/api/agent/chat/stream")
def agent_chat_stream(request: AgentChatRequest) -> StreamingResponse:
    context_override = _build_agent_context_override(request.session_id, request.context)

    def event_iterator():
        debug_trace: dict[str, object] | None = {} if _is_agent_debug_enabled() else None
        try:
            service = CONTAINER.get_agent_service()
            stream_kwargs = {
                "session_id": request.session_id,
                "user_message": request.message,
                "context_override": context_override,
            }
            signature = inspect.signature(service.stream_with_context)
            if "debug_trace" in signature.parameters:
                stream_kwargs["debug_trace"] = debug_trace
            for event in service.stream_with_context(**stream_kwargs):
                yield _encode_sse_event(event.type, event.payload)
            _log_agent_debug_trace(request, debug_trace)
        except RuntimeError as error:
            _log_agent_debug_trace(request, debug_trace)
            yield _encode_sse_event("error", {"message": str(error)})

    return StreamingResponse(
        event_iterator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/agent/context/usage", response_model=AgentContextUsageResponse)
def get_agent_context_usage(request: AgentContextUsageRequest) -> AgentContextUsageResponse:
    context_override = _build_agent_context_override(request.session_id, request.context)
    usage = CONTAINER.get_agent_context_usage().inspect(
        session_id=request.session_id,
        context_override=context_override,
    )
    return AgentContextUsageResponse(
        session_id=usage.session_id,
        scope_type=usage.scope_type,
        memory_key=usage.memory_key,
        estimated_total_tokens=usage.estimated_total_tokens,
        window_tokens=usage.window_tokens,
        reserved_output_tokens=usage.reserved_output_tokens,
        warning_threshold_tokens=usage.warning_threshold_tokens,
        compact_threshold_tokens=usage.compact_threshold_tokens,
        blocking_threshold_tokens=usage.blocking_threshold_tokens,
        remaining_tokens=usage.remaining_tokens,
        usage_percent=usage.usage_percent,
        level=usage.level,
        sources=[
            {
                "id": source.id,
                "label": source.label,
                "estimated_tokens": source.estimated_tokens,
            }
            for source in usage.sources
        ],
    )


@app.post("/api/agent/session/recover", response_model=AgentSessionRecoveryResponse)
def recover_agent_session(request: AgentSessionRecoveryRequest) -> AgentSessionRecoveryResponse:
    _context_override = _build_agent_context_override(request.session_id, request.context)
    snapshot = CONTAINER.agent_session_store.get_snapshot(request.session_id)
    if snapshot is None:
        return AgentSessionRecoveryResponse(
            session_id=request.session_id,
            restored=False,
            messages=[],
        )
    return AgentSessionRecoveryResponse(
        session_id=snapshot.session_id,
        restored=True,
        memory_key=snapshot.memory_key,
        updated_at=snapshot.updated_at,
        message_count=snapshot.message_count,
        messages=[
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in snapshot.messages
        ],
    )


@app.post("/api/agent/session/clear")
def clear_agent_session(request: AgentSessionClearRequest) -> dict[str, object]:
    context_override = _build_agent_context_override(request.session_id, request.context)
    CONTAINER.get_agent_service().clear_session(
        session_id=request.session_id,
        context_override=context_override,
    )
    return {"status": "cleared", "session_id": request.session_id}


@app.get("/api/videos/{series_id}/{video_id}/generate/progress")
async def stream_video_generation_progress(series_id: str, video_id: str) -> StreamingResponse:
    task_id = _build_task_id(series_id, video_id)
    return StreamingResponse(
        _stream_progress_events(
            tracker=CONTAINER.generation_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _build_task_id(series_id: str, video_id: str) -> str:
    return f"{series_id}/{video_id}"


def _build_model_download_task_id(model_id: str) -> str:
    return f"asr-download/{model_id}"


def _build_agent_context_override(session_id: str, request_context) -> AgentContext | None:
    if request_context is None:
        return None
    return AgentContext(
        session_id=session_id,
        scope_type=request_context.scope_type or "series",
        series_id=request_context.series_id,
        series_title=request_context.series_title,
        video_id=request_context.video_id,
        video_title=request_context.video_title,
        selected_tool=request_context.selected_tool,
    )


def _is_agent_debug_enabled() -> bool:
    try:
        return bool(load_settings(CONTAINER.config_path, CONTAINER.root_dir).debug.mode)
    except Exception:
        return False


def _log_agent_debug_trace(request: AgentChatRequest, debug_trace: dict[str, object] | None) -> None:
    if not debug_trace:
        return
    LOGGER.info(
        "Agent debug trace\nsession_id=%s\nmessage=%s\ntrace=%s",
        request.session_id,
        request.message,
        json.dumps(debug_trace, ensure_ascii=False, indent=2, default=str),
    )


def _ensure_video_exists(series_id: str, video_id: str) -> None:
    if CONTAINER.get_video_source.run(series_id, video_id) is None:
        raise HTTPException(status_code=404, detail=f"video not found '{series_id}/{video_id}'")


async def _stream_progress_events(*, tracker, task_id: str, terminal_statuses: set[str]):
    last_sequence = -1
    while True:
        snapshot = tracker.get_snapshot(task_id)
        if snapshot.sequence != last_sequence:
            last_sequence = snapshot.sequence
            yield f"data: {json.dumps(snapshot.to_dict(), ensure_ascii=False)}\n\n"
        if snapshot.status in terminal_statuses:
            break
        await asyncio.sleep(0.25)


def _encode_sse_event(event_type: str, payload: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# Bilibili Linked Series 端点

@app.post("/api/linked/bilibili/resolve/series", response_model=SeriesResponse)
async def resolve_bilibili_series(request: ResolveBilibiliSeriesRequest) -> SeriesResponse:
    try:
        series = await CONTAINER.resolve_bilibili_series.run(url=request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SeriesResponse.from_model(series)


@app.post("/api/linked/bilibili/resolve/video", response_model=VideoCardResponse)
async def resolve_bilibili_video(request: ResolveBilibiliVideoRequest) -> VideoCardResponse:
    try:
        card = await CONTAINER.resolve_bilibili_video.run(
            url=request.url,
            target_series_id=request.target_series_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VideoCardResponse.from_model(card)


@app.post("/api/videos/{series_id}/{video_id}/download", response_model=LinkedVideoDownloadResponse)
async def start_video_download(series_id: str, video_id: str) -> LinkedVideoDownloadResponse:
    try:
        result = CONTAINER.start_linked_video_download.run(series_id=series_id, video_id=video_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LinkedVideoDownloadResponse.started(result.task_id)


@app.get("/api/videos/{series_id}/{video_id}/download/progress")
async def stream_video_download_progress(series_id: str, video_id: str) -> StreamingResponse:
    task_id = build_video_download_task_id(series_id, video_id)
    return StreamingResponse(
        _stream_progress_events(
            tracker=CONTAINER.video_download_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.delete("/api/linked/{series_id}")
def delete_linked_series(series_id: str) -> dict[str, object]:
    try:
        deleted = CONTAINER.delete_linked_series.run(series_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "series_id": deleted.series_id}
