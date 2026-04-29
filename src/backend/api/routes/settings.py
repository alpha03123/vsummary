from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.container import ApiContainerDep
from backend.api.contracts import (
    FasterWhisperModelResponse,
    ProviderSettingsResponse,
    UpdateProviderSettingsRequest,
    UpdateWorkspaceSettingsRequest,
    WorkspaceSettingsResponse,
)
from backend.api.settings_service import ProviderSettingsUpdate, SettingsValidationError, WorkspaceSettingsUpdate
from backend.api.sse import stream_progress_events
from backend.video_summary.infrastructure.settings import load_settings

router = APIRouter()


@router.get("/api/settings", response_model=WorkspaceSettingsResponse)
def get_workspace_settings(container: ApiContainerDep) -> WorkspaceSettingsResponse:
    settings = container.settings_service.get_workspace_settings()
    return WorkspaceSettingsResponse(
        theme=settings.theme,
        show_takeaways=settings.show_takeaways,
        transcript_enhancement_enabled=settings.transcript_enhancement_enabled,
        asr_model_quality=settings.asr_model_quality,
        transcription_mode=settings.transcription_mode,
    )


@router.put("/api/settings", response_model=WorkspaceSettingsResponse)
def update_workspace_settings(
    request: UpdateWorkspaceSettingsRequest,
    container: ApiContainerDep,
) -> WorkspaceSettingsResponse:
    try:
        settings = container.settings_service.update_workspace_settings(
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


@router.get("/api/provider-settings", response_model=ProviderSettingsResponse)
def get_provider_settings(container: ApiContainerDep) -> ProviderSettingsResponse:
    env_settings = container.settings_service.get_provider_settings()
    return ProviderSettingsResponse(
        llm_provider=env_settings.llm_provider,
        openai_base_url=env_settings.openai_base_url,
        openai_model=env_settings.openai_model,
        has_openai_api_key=env_settings.has_openai_api_key,
        openai_api_key_masked=env_settings.openai_api_key_masked,
    )


@router.put("/api/provider-settings", response_model=ProviderSettingsResponse)
def update_provider_settings(
    request: UpdateProviderSettingsRequest,
    container: ApiContainerDep,
) -> ProviderSettingsResponse:
    try:
        env_settings = container.settings_service.update_provider_settings(
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


@router.get("/api/asr/faster-whisper/models", response_model=list[FasterWhisperModelResponse])
def list_faster_whisper_models(container: ApiContainerDep) -> list[FasterWhisperModelResponse]:
    settings = load_settings(container.config_path, container.root_dir)
    return [
        FasterWhisperModelResponse(
            id=model.id,
            label=model.label,
            downloaded=model.downloaded,
            current=model.current,
            recommended=model.recommended,
        )
        for model in container.faster_whisper_model_manager.list_models(settings.asr.faster_whisper.model_size)
    ]


@router.post("/api/asr/faster-whisper/models/{model_id}/download", response_model=FasterWhisperModelResponse)
def download_faster_whisper_model(model_id: str, container: ApiContainerDep) -> FasterWhisperModelResponse:
    if not container.faster_whisper_model_manager.is_supported(model_id):
        raise HTTPException(status_code=400, detail=f"unsupported faster-whisper model '{model_id}'")

    reporter = container.model_download_progress_tracker.create_reporter(_build_model_download_task_id(model_id))
    try:
        container.faster_whisper_model_manager.download(model_id, progress_reporter=reporter)
    except Exception as error:
        if "取消" in str(error):
            reporter.cancelled("模型下载已取消")
            raise HTTPException(status_code=409, detail="模型下载已取消") from error
        reporter.failed(str(error))
        raise
    settings = load_settings(container.config_path, container.root_dir)
    downloaded_model = next(
        model
        for model in container.faster_whisper_model_manager.list_models(settings.asr.faster_whisper.model_size)
        if model.id == model_id
    )
    return FasterWhisperModelResponse(
        id=downloaded_model.id,
        label=downloaded_model.label,
        downloaded=downloaded_model.downloaded,
        current=downloaded_model.current,
        recommended=downloaded_model.recommended,
    )


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


@router.post("/api/asr/faster-whisper/models/{model_id}/download/cancel")
def cancel_faster_whisper_model_download(model_id: str, container: ApiContainerDep) -> dict[str, object]:
    container.model_download_progress_tracker.request_cancel(_build_model_download_task_id(model_id))
    return {"status": "cancelled"}


def _build_model_download_task_id(model_id: str) -> str:
    return f"asr-download/{model_id}"
