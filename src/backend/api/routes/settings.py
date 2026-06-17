"""工作区设置与模型管理路由。

提供工作区设置读写、模型供应商配置、ASR/RAG 模型列表与下载、
以及连接测试的 HTTP 端点。
"""

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
from backend.video_summary.infrastructure.settings import load_settings

router = APIRouter()
_ASR_DOWNLOAD_LOCK = Lock()
_ACTIVE_ASR_DOWNLOADS: set[str] = set()


@router.get("/api/settings", response_model=WorkspaceSettingsResponse)
def get_workspace_settings(container: ApiContainerDep) -> WorkspaceSettingsResponse:
    """GET /api/settings — 获取当前工作区设置。

    返回工作区全部可配参数（主题、ASR 质量、RAG 参数、
    token 窗口、推理强度等）的当前值。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        WorkspaceSettingsResponse，含完整的工作区配置。

    Raises:
        HTTPException(400): 配置文件读取异常。
    """
    try:
        settings = container.settings_service.get_workspace_settings()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return WorkspaceSettingsResponse(
        theme=settings.theme,
        show_takeaways=settings.show_takeaways,
        layout_mode=settings.layout_mode,
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
    """PUT /api/settings — 更新工作区设置。

    全量写入所有可配参数到配置文件；更新后自动让 Agent 图服务
    失效以便下次调用时重建，并同步调整视频生成并发度和超星延迟配置。

    Args:
        request: 包含所有可更新字段的请求体（字段均为可选）。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        WorkspaceSettingsResponse，含更新后的完整配置。

    Raises:
        HTTPException(400): 配置值无效。
    """
    try:
        settings = container.settings_service.update_workspace_settings(
            theme=request.theme,
            show_takeaways=request.show_takeaways,
            layout_mode=request.layout_mode,
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
        layout_mode=settings.layout_mode,
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
    """GET /api/provider-settings — 获取模型供应商配置。

    返回 LLM 供应商、base URL、模型名、API Key 掩码和 HF 镜像地址；
    API Key 原文不返回，仅返回掩码和布尔标记。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        ProviderSettingsResponse，含供应商配置详情。

    Raises:
        HTTPException(400): 配置文件读取异常。
    """
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
    """GET /api/provider-settings/openai-api-key — 获取 OpenAI API Key 原文。

    仅在用户主动请求查看时返回完整 Key，默认接口只返回掩码；
    用于用户在设置面板中确认或复制当前 Key。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        ProviderApiKeyResponse，含完整的 openai_api_key。
    """
    return ProviderApiKeyResponse(openai_api_key=container.settings_service.get_openai_api_key())


@router.put("/api/provider-settings", response_model=ProviderSettingsResponse)
def update_provider_settings(
    request: UpdateProviderSettingsRequest,
    container: ApiContainerDep,
) -> ProviderSettingsResponse:
    """PUT /api/provider-settings — 更新模型供应商配置。

    写入 LLM 供应商、base URL、模型名、API Key 和 HF 镜像地址；
    写入后自动让 Agent 图服务失效。

    Args:
        request: 包含供应商配置字段的请求体。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        ProviderSettingsResponse，含更新后的供应商配置。

    Raises:
        HTTPException(400): 配置值无效。
    """
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
    """POST /api/provider-settings/test — 测试模型供应商连接。

    用请求中的供应商配置发起一次实际 LLM 调用以验证连通性；
    不持久化配置，仅返回连接测试结果。

    Args:
        request: 包含待测试供应商配置的请求体。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        TestProviderSettingsResponse，含 ok=True 及成功消息。

    Raises:
        HTTPException(400): 配置值无效。
        HTTPException(503): 模型服务调用失败。
    """
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
    """GET /api/asr/faster-whisper/models — 列出可用的 faster-whisper ASR 模型。

    返回满足当前 model_size 配置的所有可用模型及其下载状态、
    推荐标记、当前进度等信息。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        FasterWhisperModelResponse 列表。

    Raises:
        HTTPException(400): 配置文件读取异常。
    """
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
    """POST /api/asr/faster-whisper/models/{model_id}/download — 触发 faster-whisper 模型下载。

    在后台线程启动模型下载，同一模型同时只允许一个下载任务；
    返回模型当前信息（含下载进度），前端通过对应的 SSE 端点订阅进度。

    Args:
        model_id: 模型 ID，来自模型列表响应。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        FasterWhisperModelResponse，含当前下载状态与进度。

    Raises:
        HTTPException(400): 不支持的模型 ID。
    """
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
    """GET /api/asr/faster-whisper/models/{model_id}/download/progress — 订阅 ASR 模型下载进度流（SSE）。

    以 SSE 推送模型下载的状态变化与进度百分比；
    到达 completed、failed 或 cancelled 终端状态后自动关闭流。

    Args:
        model_id: 模型 ID。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。
    """
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
    """GET /api/rag/models — 列出可用的 RAG 嵌入模型。

    返回所有 RAG 模型及其下载状态、用途（embedding/reranker）等信息。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        RagModelResponse 列表。
    """
    return [_to_rag_model_response(model) for model in container.rag_model_manager.list_models()]


@router.post("/api/rag/models/{model_key}/download", response_model=RagModelResponse)
def download_rag_model(model_key: str, container: ApiContainerDep) -> RagModelResponse:
    """POST /api/rag/models/{model_key}/download — 触发 RAG 模型下载。

    启动指定 RAG 模型的下载任务；若已在下载则返回当前进度。

    Args:
        model_key: 模型 key，来自模型列表响应。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        RagModelResponse，含当前下载状态与进度。

    Raises:
        HTTPException(400): 不支持的模型 key。
    """
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
    """GET /api/rag/models/{model_key}/download/progress — 订阅 RAG 模型下载进度流（SSE）。

    以 SSE 推送 RAG 模型下载的状态变化与进度百分比；
    到达 completed、failed 或 cancelled 终端状态后自动关闭流。

    Args:
        model_key: 模型 key。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`）。

    Raises:
        HTTPException(400): 无效的模型 key。
    """
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
    """构建 ASR 模型下载的进度跟踪任务 ID。

    Args:
        model_id: 模型 ID。

    Returns:
        格式为 `asr-download/{model_id}` 的任务 ID。
    """
    return f"asr-download/{model_id}"


def _run_faster_whisper_model_download(model_id: str, task_id: str, container: ApiContainerDep, reporter) -> None:
    """在后台线程中执行 faster-whisper 模型下载。

    完成后自动清理 `_ACTIVE_ASR_DOWNLOADS` 集合中的任务记录。

    Args:
        model_id: 模型 ID。
        task_id: 进度跟踪任务 ID。
        container: API 容器。
        reporter: 进度报告器。
    """
    try:
        container.faster_whisper_model_manager.download(model_id, progress_reporter=reporter)
    except Exception as error:
        reporter.failed(str(error))
    finally:
        with _ASR_DOWNLOAD_LOCK:
            _ACTIVE_ASR_DOWNLOADS.discard(task_id)


def _to_faster_whisper_model_response(model, container: ApiContainerDep) -> FasterWhisperModelResponse:
    """将 faster-whisper 模型对象转换为 API 响应 DTO，含当前下载进度快照。

    Args:
        model: 模型元数据对象。
        container: API 容器。

    Returns:
        附加了下载进度的 FasterWhisperModelResponse。
    """
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
    """将 RAG 模型对象转换为 API 响应 DTO。

    Args:
        model: RAG 模型元数据对象。

    Returns:
        RagModelResponse。
    """
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
