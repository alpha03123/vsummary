"""Agent 聊天与会话管理路由。

提供 Agent 对话（流式/非流式）、Session 生命周期管理、
上下文预算查询和知识记忆状态监控的 HTTP 端点。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.agent.memory.context import AgentContext
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult, ScopeType
from backend.api.container import ApiContainerDep
from backend.api.responses import (
    AgentChatRequest,
    AgentChatResponse,
    AgentContextUsageRequest,
    AgentContextUsageResponse,
    AgentSessionClearRequest,
    AgentSessionRecoveryRequest,
    AgentSessionRecoveryResponse,
    CitationResponse,
)
from backend.api.sse import encode_sse_event
from backend.video_summary.infrastructure.rag_models import (
    RAG_EMBEDDING_REQUIRED_MESSAGE,
    RAG_MODEL_DOWNLOAD_MESSAGE,
)
from backend.video_summary.infrastructure.settings import load_settings

LOGGER = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/agent/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest, container: ApiContainerDep) -> AgentChatResponse:
    """POST /api/agent/chat — 非流式 Agent 对话。

    将用户消息送入 LangGraph Agent 图执行完整的一次推理回合，
    返回最终回答、Action Plan 和引文列表。
    若 RAG 模型未就绪则直接返回阻断提示，不执行 Agent 图。

    Args:
        request: 包含 session_id、消息文本和可选上下文的 DTO。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        AgentChatResponse，含 assistant_message、plan 和 citations。

    Raises:
        HTTPException(503): Agent 图执行过程中发生异常。
    """
    context_override = _build_agent_context_override(request.session_id, request.context)
    rag_block_message = _resolve_rag_block_message(context_override, container)
    if rag_block_message:
        return _build_rag_block_response(context_override, rag_block_message)

    try:
        result = container.get_agent_graph_service().run_turn(
            session_id=request.session_id,
            user_message=request.message,
            context_override=context_override,
        )
    except Exception as error:
        LOGGER.exception("Agent chat failed")
        raise HTTPException(status_code=503, detail=_format_agent_error(error)) from error
    return AgentChatResponse.from_result(result)


@router.post("/api/agent/chat/stream")
def agent_chat_stream(request: AgentChatRequest, container: ApiContainerDep) -> StreamingResponse:
    """POST /api/agent/chat/stream — 流式 Agent 对话（SSE）。

    与 `/api/agent/chat` 共享同一请求体，但以 Server-Sent Events 流
    逐步推送思考、Action、回答和引文事件，前端可逐 token 渲染。
    若 RAG 模型未就绪则推送阻断消息后立即结束流。

    Args:
        request: 包含 session_id、消息文本和可选上下文的 DTO。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        StreamingResponse（`text/event-stream`），逐个推送 Agent 执行事件。

    Raises:
        异常不直接向 HTTP 抛出，而是编码为 ``error`` SSE 事件推送。
    """
    context_override = _build_agent_context_override(request.session_id, request.context)

    def event_iterator():
        rag_block_message = _resolve_rag_block_message(context_override, container)
        if rag_block_message:
            yield from _stream_rag_block_message(rag_block_message)
            return
        debug_trace: dict[str, object] | None = {} if _is_agent_debug_enabled(container) else None
        try:
            service = container.get_agent_graph_service()
            for event in service.stream_with_context(
                session_id=request.session_id,
                user_message=request.message,
                context_override=context_override,
                debug_trace=debug_trace,
            ):
                yield encode_sse_event(event.type, event.payload)
            _log_agent_debug_trace(request, debug_trace)
        except Exception as error:
            _log_agent_debug_trace(request, debug_trace)
            LOGGER.exception("Agent chat stream failed")
            yield encode_sse_event("error", {"message": _format_agent_error(error)})

    return StreamingResponse(
        event_iterator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/api/agent/context/usage", response_model=AgentContextUsageResponse)
def get_agent_context_usage(request: AgentContextUsageRequest, container: ApiContainerDep) -> AgentContextUsageResponse:
    """POST /api/agent/context/usage — 查询上下文预算使用情况。

    返回当前 session 的 token 预算快照，包括各来源（system prompt、
    历史消息、RAG 文档等）的估算 token 数及使用百分比，
    前端据此决定是否需要压缩上下文。

    Args:
        request: 包含 session_id 和可选上下文范围的 DTO。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        AgentContextUsageResponse，含 token 使用详情与告警级别。
    """
    context_override = _build_agent_context_override(request.session_id, request.context)
    usage = container.get_agent_context_usage().inspect(
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


@router.get("/api/agent/memory/status")
def get_agent_memory_status(container: ApiContainerDep) -> dict[str, object]:
    """GET /api/agent/memory/status — 查询知识记忆刷新进度。

    返回后台知识记忆刷新任务的状态快照（进度百分比、状态、详情），
    前端按需轮询此端点以展示刷新进度条。

    Args:
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        包含 status、progress、detail 等字段的进度快照字典。
    """
    return container.knowledge_memory_progress_tracker.get_snapshot("agent-memory-refresh").to_dict()


@router.post("/api/agent/session/recover", response_model=AgentSessionRecoveryResponse)
def recover_agent_session(request: AgentSessionRecoveryRequest, container: ApiContainerDep) -> AgentSessionRecoveryResponse:
    """POST /api/agent/session/recover — 恢复 Agent Session。

    从 session 持久化存储中取出指定 session 的历史消息快照，
    若 session 不存在则返回 restored=False 的空结果。

    Args:
        request: 包含待恢复 session_id 的 DTO。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        AgentSessionRecoveryResponse，含 restored 标记、消息列表及元数据。
    """
    snapshot = container.agent_session_store.get_snapshot(request.session_id)
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
                "citations": [CitationResponse.from_model(item) for item in message.citations],
            }
            for message in snapshot.messages
        ],
    )


@router.post("/api/agent/session/clear")
def clear_agent_session(request: AgentSessionClearRequest, container: ApiContainerDep) -> dict[str, object]:
    """POST /api/agent/session/clear — 清除 Agent Session。

    删除指定 session 的所有持久化消息记录，
    用于用户主动重置对话上下文。

    Args:
        request: 包含待清除 session_id 的 DTO。
        container: FastAPI 依赖注入的 API 容器。

    Returns:
        {"status": "cleared", "session_id": ...}
    """
    session_store = getattr(container, "agent_session_store", None)
    if session_store is not None:
        session_store.clear_snapshot(request.session_id)
    return {"status": "cleared", "session_id": request.session_id}


def _build_agent_context_override(session_id: str, request_context) -> AgentContext | None:
    """根据请求中的上下文字段构建 `AgentContext` 覆盖对象。

    Args:
        session_id: 当前 session ID。
        request_context: 请求中携带的上下文 DTO。

    Returns:
        若请求上下文为 None 则返回 None，否则返回填充后的 `AgentContext`。
    """
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


def _resolve_rag_block_message(context: AgentContext | None, container) -> str | None:
    """检测当前 scope 是否需要 RAG 模型但模型未就绪，返回阻断提示。

    Args:
        context: Agent 上下文（若为 None 或非 series scope 则不阻断）。
        container: API 容器。

    Returns:
        若 RAG 模型正在下载或尚未下载则返回中文提示文案，否则返回 None。
    """
    if context is None or context.scope_type != ScopeType.SERIES.value:
        return None
    rag_model_manager = getattr(container, "rag_model_manager", None)
    if rag_model_manager is None:
        return None
    if rag_model_manager.has_active_download():
        return RAG_MODEL_DOWNLOAD_MESSAGE
    if not rag_model_manager.is_downloaded("embedding"):
        return RAG_EMBEDDING_REQUIRED_MESSAGE
    return None


def _build_rag_block_response(context: AgentContext | None, message: str) -> AgentChatResponse:
    """构造一个“RAG 模型不可用”的占位 AgentTurnResult 响应。

    Args:
        context: 原始 Agent 上下文（用于推断 scope_type）。
        message: 要返回给用户的阻断提示文案。

    Returns:
        包装后的 AgentChatResponse。
    """
    scope_type = ScopeType.SERIES if context is None or context.scope_type == ScopeType.SERIES.value else ScopeType.VIDEO
    return AgentChatResponse.from_result(
        AgentTurnResult(
            assistant_message=message,
            plan=AgentActionPlan(
                scope_type=scope_type,
                reason="rag_model_unavailable",
                tool_calls=[],
                use_answerer=False,
            ),
            tool_results=[],
            citations=[],
        )
    )


def _stream_rag_block_message(message: str):
    """生成“RAG 模型不可用”的 SSE 阻断消息事件流。

    Args:
        message: 阻断提示文案。

    Yields:
        依次推送 answer_started、answer_delta、answer_completed 三个 SSE 事件。
    """
    yield encode_sse_event("answer_started", {"message": "正在检查 RAG 模型"})
    yield encode_sse_event("answer_delta", {"delta": message})
    yield encode_sse_event("answer_completed", {"message": message, "citations": []})


def _format_agent_error(error: Exception) -> str:
    """将 Agent 执行异常按错误特征翻译为中文友好提示。

    识别场景包括：联网搜索超时、模型不支持联网搜索、URL 连接失败、
    模型被上游拦截、通用 LiteLLM 错误等。

    Args:
        error: 原始异常对象。

    Returns:
        面向终端用户的中文错误提示字符串。
    """
    message = str(error).strip()
    if _is_web_search_timeout(error, message):
        return "联网搜索失败：请求超时，请稍后重试或关闭联网搜索。"
    if _is_unsupported_web_search_error(message):
        return "联网搜索失败：当前模型或供应商不支持联网搜索，请关闭联网搜索或更换支持搜索的模型。"
    if _is_web_search_error(message):
        return f"联网搜索失败：{message}" if message else "联网搜索失败。"
    if _is_model_url_connection_error(message):
        return "url连接错误，请检查拼写或者地址是否可用"
    if "Your request was blocked" in message:
        return "模型请求被上游网关拦截，请检查模型供应商、API 网关或更换官方 API 地址。"
    if "APIError" in message or "OpenAIException" in message or "litellm" in type(error).__module__:
        return f"模型服务调用失败：{message}" if message else "模型服务调用失败。"
    return message or "AI 对话失败。"


def _is_web_search_timeout(error: Exception, message: str) -> bool:
    """判断异常是否是联网搜索超时错误。"""
    normalized = message.lower()
    return (
        ("web_search" in normalized or "联网搜索" in message)
        and (isinstance(error, TimeoutError) or "timeout" in normalized or "timed out" in normalized)
    )


def _is_unsupported_web_search_error(message: str) -> bool:
    """判断错误消息是否表示当前模型不支持联网搜索。"""
    normalized = message.lower()
    if "web_search_options" not in normalized and "web_search" not in normalized and "联网搜索" not in message:
        return False
    unsupported_markers = (
        "unsupported",
        "not supported",
        "unrecognized",
        "unknown parameter",
        "invalid parameter",
        "does not support",
        "不支持",
    )
    return any(marker in normalized for marker in unsupported_markers)


def _is_web_search_error(message: str) -> bool:
    """判断错误消息是否与联网搜索相关。"""
    normalized = message.lower()
    return "web_search" in normalized or "web_search_options" in normalized or "联网搜索" in message


def _is_model_url_connection_error(message: str) -> bool:
    """判断错误消息是否表示模型 URL 连接失败。"""
    normalized = message.lower()
    connection_markers = (
        "connection error",
        "connecterror",
        "apiconnectionerror",
        "connection refused",
        "name or service not known",
        "nodename nor servname provided",
        "failed to resolve",
        "getaddrinfo failed",
        "temporary failure in name resolution",
        "无法连接",
        "连接失败",
        "拒绝连接",
    )
    return any(marker in normalized for marker in connection_markers)


def _is_agent_debug_enabled(container) -> bool:
    """检查配置中是否启用了 Agent 调试模式。"""
    try:
        return bool(load_settings(container.config_path, container.root_dir).debug.mode)
    except Exception:
        return False


def _log_agent_debug_trace(request: AgentChatRequest, debug_trace: dict[str, object] | None) -> None:
    """记录 Agent 调试跟踪信息到日志。

    仅在 debug_trace 非空时执行，将 session_id、用户消息和
    完整的 LangGraph 执行路径以 JSON 格式输出。
    """
    if not debug_trace:
        return
    LOGGER.info(
        "Agent debug trace\nsession_id=%s\nmessage=%s\ntrace=%s",
        request.session_id,
        request.message,
        json.dumps(debug_trace, ensure_ascii=False, indent=2, default=str),
    )
