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
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return AgentChatResponse.from_result(result)


@router.post("/api/agent/chat/stream")
def agent_chat_stream(request: AgentChatRequest, container: ApiContainerDep) -> StreamingResponse:
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
        except RuntimeError as error:
            _log_agent_debug_trace(request, debug_trace)
            yield encode_sse_event("error", {"message": str(error)})

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
    return container.knowledge_memory_progress_tracker.get_snapshot("agent-memory-refresh").to_dict()


@router.post("/api/agent/session/recover", response_model=AgentSessionRecoveryResponse)
def recover_agent_session(request: AgentSessionRecoveryRequest, container: ApiContainerDep) -> AgentSessionRecoveryResponse:
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
            }
            for message in snapshot.messages
        ],
    )


@router.post("/api/agent/session/clear")
def clear_agent_session(request: AgentSessionClearRequest, container: ApiContainerDep) -> dict[str, object]:
    session_store = getattr(container, "agent_session_store", None)
    if session_store is not None:
        session_store.clear_snapshot(request.session_id)
    return {"status": "cleared", "session_id": request.session_id}


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


def _resolve_rag_block_message(context: AgentContext | None, container) -> str | None:
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
    yield encode_sse_event("answer_started", {"message": "正在检查 RAG 模型"})
    yield encode_sse_event("answer_delta", {"delta": message})
    yield encode_sse_event("answer_completed", {"message": message, "citations": []})


def _is_agent_debug_enabled(container) -> bool:
    try:
        return bool(load_settings(container.config_path, container.root_dir).debug.mode)
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
