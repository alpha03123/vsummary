from __future__ import annotations

from threading import Lock
from threading import Thread

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.contracts import (
    FasterWhisperModelResponse,
    ProviderApiKeyResponse,
    ProviderSettingsResponse,
    RagModelResponse,
    TestProviderSettingsResponse,
    UpdateProviderSettingsRequest,
    UpdateWorkspaceSettingsRequest,
    WorkspaceSettingsResponse,
)
from backend.api.sse import stream_progress_events
from backend.video_summary.configuration.settings import load_settings

router = APIRouter()
_ASR_DOWNLOAD_LOCK = Lock()
_ACTIVE_ASR_DOWNLOADS: set[str] = set()


@router.get("/api/settings", response_model=WorkspaceSettingsResponse)
def get_workspace_settings(container: ApiContainerDep) -> WorkspaceSettingsResponse:
    try:
        settings = container.settings_service.get_workspace_settings()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return WorkspaceSettingsResponse(
        theme=settings.theme,
        show_takeaways=settings.show_takeaways,
        transcript_enhancement_enabled=settings.transcript_enhancement_enabled,
        asr_model_quality=settings.asr_model_quality,
        transcription_mode=settings.transcription_mode,
        rag_embedding_device=settings.rag_embedding_device,
        rag_max_hits=settings.rag_max_hits,
        rag_rerank_enabled=settings.rag_rerank_enabled,
        window_tokens=settings.window_tokens,
        answer_detail_level=settings.answer_detail_level,
        reasoning_effort=settings.reasoning_effort,
        talk_custom_prompt=settings.talk_custom_prompt,
        video_generation_concurrency=settings.video_generation_concurrency,
        web_search_enabled=settings.web_search_enabled,
        chaoxing_request_delay_seconds=settings.chaoxing_request_delay_seconds,
        chaoxing_init_course_delay_seconds=settings.chaoxing_init_course_delay_seconds,
    )


@router.put("/api/settings", response_model=WorkspaceSettingsResponse)
async def update_workspace_settings(
    request: UpdateWorkspaceSettingsRequest,
    container: ApiContainerDep,
) -> WorkspaceSettingsResponse:
    try:
        settings = container.settings_service.update_workspace_settings(
            theme=request.theme,
            show_takeaways=request.show_takeaways,
            transcript_enhancement_enabled=request.transcript_enhancement_enabled,
            asr_model_quality=request.asr_model_quality,
            transcription_mode=request.transcription_mode,
            rag_embedding_device=request.rag_embedding_device,
            rag_max_hits=request.rag_max_hits,
            rag_rerank_enabled=request.rag_rerank_enabled,
            window_tokens=request.window_tokens,
            answer_detail_level=request.answer_detail_level,
            reasoning_effort=request.reasoning_effort,
            talk_custom_prompt=request.talk_custom_prompt,
            video_generation_concurrency=request.video_generation_concurrency,
            web_search_enabled=request.web_search_enabled,
            chaoxing_request_delay_seconds=request.chaoxing_request_delay_seconds,
            chaoxing_init_course_delay_seconds=request.chaoxing_init_course_delay_seconds,
        )
        container.invalidate_agent_graph_service()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    container.generate_video_summary.update_video_generation_concurrency(
        settings.video_generation_concurrency
    )
    container.chaoxing_importer.configure_delays(
        request_delay_seconds=settings.chaoxing_request_delay_seconds,
        init_course_delay_seconds=settings.chaoxing_init_course_delay_seconds,
    )

    return WorkspaceSettingsResponse(
        theme=settings.theme,
        show_takeaways=settings.show_takeaways,
        transcript_enhancement_enabled=settings.transcript_enhancement_enabled,
        asr_model_quality=settings.asr_model_quality,
        transcription_mode=settings.transcription_mode,
        rag_embedding_device=settings.rag_embedding_device,
        rag_max_hits=settings.rag_max_hits,
        rag_rerank_enabled=settings.rag_rerank_enabled,
        window_tokens=settings.window_tokens,
        answer_detail_level=settings.answer_detail_level,
        reasoning_effort=settings.reasoning_effort,
        talk_custom_prompt=settings.talk_custom_prompt,
        video_generation_concurrency=settings.video_generation_concurrency,
        web_search_enabled=settings.web_search_enabled,
        chaoxing_request_delay_seconds=settings.chaoxing_request_delay_seconds,
        chaoxing_init_course_delay_seconds=settings.chaoxing_init_course_delay_seconds,
    )


@router.get("/api/provider-settings", response_model=ProviderSettingsResponse)
def get_provider_settings(container: ApiContainerDep) -> ProviderSettingsResponse:
    try:
        env_settings = container.settings_service.get_provider_settings()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ProviderSettingsResponse(
        llm_provider=env_settings.llm_provider,
        openai_base_url=env_settings.openai_base_url,
        openai_model=env_settings.openai_model,
        has_openai_api_key=env_settings.has_openai_api_key,
        openai_api_key_masked=env_settings.openai_api_key_masked,
        hf_endpoint=env_settings.hf_endpoint,
    )


@router.get("/api/provider-settings/openai-api-key", response_model=ProviderApiKeyResponse)
def get_provider_openai_api_key(container: ApiContainerDep) -> ProviderApiKeyResponse:
    return ProviderApiKeyResponse(openai_api_key=container.settings_service.get_openai_api_key())


@router.put("/api/provider-settings", response_model=ProviderSettingsResponse)
def update_provider_settings(
    request: UpdateProviderSettingsRequest,
    container: ApiContainerDep,
) -> ProviderSettingsResponse:
    try:
        env_settings = container.settings_service.update_provider_settings(
            llm_provider=request.llm_provider,
            openai_base_url=request.openai_base_url,
            openai_model=request.openai_model,
            openai_api_key=request.openai_api_key,
            hf_endpoint=request.hf_endpoint,
        )
        container.invalidate_agent_graph_service()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return ProviderSettingsResponse(
        llm_provider=env_settings.llm_provider,
        openai_base_url=env_settings.openai_base_url,
        openai_model=env_settings.openai_model,
        has_openai_api_key=env_settings.has_openai_api_key,
        openai_api_key_masked=env_settings.openai_api_key_masked,
        hf_endpoint=env_settings.hf_endpoint,
    )


@router.post("/api/provider-settings/test", response_model=TestProviderSettingsResponse)
def test_provider_settings(
    request: UpdateProviderSettingsRequest,
    container: ApiContainerDep,
) -> TestProviderSettingsResponse:
    try:
        response = container.settings_service.test_provider_settings(
            llm_provider=request.llm_provider,
            openai_base_url=request.openai_base_url,
            openai_model=request.openai_model,
            openai_api_key=request.openai_api_key,
            hf_endpoint=request.hf_endpoint,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return TestProviderSettingsResponse(ok=True, message=f"模型连接成功：{response}")


@router.get("/api/asr/faster-whisper/models", response_model=list[FasterWhisperModelResponse])
def list_faster_whisper_models(container: ApiContainerDep) -> list[FasterWhisperModelResponse]:
    try:
        settings = load_settings(container.config_path, container.root_dir)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return [
        _to_faster_whisper_model_response(model, container)
        for model in container.faster_whisper_model_manager.list_models(settings.asr.faster_whisper.model_size)
    ]


@router.post("/api/asr/faster-whisper/models/{model_id}/download", response_model=FasterWhisperModelResponse)
def download_faster_whisper_model(model_id: str, container: ApiContainerDep) -> FasterWhisperModelResponse:
    if not container.faster_whisper_model_manager.is_supported(model_id):
        raise HTTPException(status_code=400, detail=f"unsupported faster-whisper model '{model_id}'")

    task_id = _build_model_download_task_id(model_id)
    should_start = False
    with _ASR_DOWNLOAD_LOCK:
        if task_id not in _ACTIVE_ASR_DOWNLOADS:
            _ACTIVE_ASR_DOWNLOADS.add(task_id)
            should_start = True

    if should_start:
        reporter = container.model_download_progress_tracker.create_reporter(task_id)
        Thread(
            target=_run_faster_whisper_model_download,
            args=(model_id, task_id, container, reporter),
            daemon=True,
        ).start()

    settings = load_settings(container.config_path, container.root_dir)
    downloaded_model = next(
        model
        for model in container.faster_whisper_model_manager.list_models(settings.asr.faster_whisper.model_size)
        if model.id == model_id
    )
    return _to_faster_whisper_model_response(downloaded_model, container)


@router.get("/api/asr/faster-whisper/models/{model_id}/download/progress")
async def stream_faster_whisper_model_download_progress(
    model_id: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    task_id = _build_model_download_task_id(model_id)
    return StreamingResponse(
        stream_progress_events(
            tracker=container.model_download_progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/rag/models", response_model=list[RagModelResponse])
def list_rag_models(container: ApiContainerDep) -> list[RagModelResponse]:
    return [_to_rag_model_response(model) for model in container.rag_model_manager.list_models()]


@router.post("/api/rag/models/{model_key}/download", response_model=RagModelResponse)
def download_rag_model(model_key: str, container: ApiContainerDep) -> RagModelResponse:
    try:
        status = container.rag_model_manager.start_download(model_key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _to_rag_model_response(status)


@router.get("/api/rag/models/{model_key}/download/progress")
async def stream_rag_model_download_progress(
    model_key: str,
    container: ApiContainerDep,
) -> StreamingResponse:
    try:
        task_id = container.rag_model_manager.stream_task_id(model_key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StreamingResponse(
        stream_progress_events(
            tracker=container.rag_model_manager.progress_tracker,
            task_id=task_id,
            terminal_statuses={"completed", "failed", "cancelled"},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


def _build_model_download_task_id(model_id: str) -> str:
    return f"asr-download/{model_id}"


def _run_faster_whisper_model_download(model_id: str, task_id: str, container: ApiContainerDep, reporter) -> None:
    try:
        container.faster_whisper_model_manager.download(model_id, progress_reporter=reporter)
    except Exception as error:
        reporter.failed(str(error))
    finally:
        with _ASR_DOWNLOAD_LOCK:
            _ACTIVE_ASR_DOWNLOADS.discard(task_id)


def _to_faster_whisper_model_response(model, container: ApiContainerDep) -> FasterWhisperModelResponse:
    snapshot = container.model_download_progress_tracker.get_snapshot(_build_model_download_task_id(model.id))
    return FasterWhisperModelResponse(
        id=model.id,
        label=model.label,
        downloaded=model.downloaded,
        current=model.current,
        recommended=model.recommended,
        status=snapshot.status,
        progress=snapshot.progress,
        detail=snapshot.detail,
        error=snapshot.error,
    )


def _to_rag_model_response(model) -> RagModelResponse:
    return RagModelResponse(
        key=model.key,
        label=model.label,
        repo_id=model.repo_id,
        local_path=model.local_path,
        purpose=model.purpose,
        downloaded=model.downloaded,
        status=model.status,
        progress=model.progress,
        detail=model.detail,
        error=model.error,
    )
