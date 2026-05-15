from __future__ import annotations

from collections.abc import Iterator

from backend.agent.memory.messages import MemoryMessageCompactor
from backend.agent.ports import AgentContextLoader, ChatGateway
from backend.agent.schemas.action_plan import AgentTurnResult
from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent_graph.runtime.session_recorder import AgentGraphSessionRecorder
from backend.agent_graph.runtime.streaming import AgentGraphStreamOrchestrator
from backend.agent_graph.runtime.turns import (
    AgentGraphInputBuilder,
    AgentGraphTurnBuilder,
)


class AgentGraphService:
    def __init__(
        self,
        *,
        context_loader: AgentContextLoader,
        graph,
        session_store=None,
        memory_compactor: MemoryMessageCompactor | None = None,
        answer_stream_gateway: ChatGateway | None = None,
    ) -> None:
        self._graph = graph
        self._input_builder = AgentGraphInputBuilder(
            context_loader=context_loader,
            session_store=session_store,
        )
        self._turn_builder = AgentGraphTurnBuilder()
        self._session_recorder = AgentGraphSessionRecorder(
            session_store=session_store,
            memory_compactor=memory_compactor,
        )
        self._stream_orchestrator = AgentGraphStreamOrchestrator(
            graph=graph,
            invoke_graph=self._invoke_graph,
            turn_builder=self._turn_builder,
            session_recorder=self._session_recorder,
            answer_streamer=(
                self._stream_deferred_answer
                if answer_stream_gateway is not None
                else None
            ),
        )
        self._answer_stream_gateway = answer_stream_gateway

    def _record_debug_input(
        self,
        *,
        debug_trace: dict[str, object] | None,
        graph_input: dict[str, object],
    ) -> None:
        if debug_trace is None:
            return
        debug_trace["graph_input"] = {
            "session_id": graph_input["session_id"],
            "scope_type": graph_input["scope_type"],
            "series_id": graph_input["series_id"],
            "video_id": graph_input["video_id"],
            "memory_message_count": len(graph_input["memory_messages"]),
            "memory_messages": graph_input["memory_messages"],
            "user_message": graph_input["user_message"],
        }

    def _invoke_graph(
        self,
        *,
        graph,
        graph_input: dict[str, object],
        debug_trace: dict[str, object] | None = None,
    ) -> dict[str, object]:
        result = graph.invoke(graph_input)
        if debug_trace is not None:
            debug_trace["graph_result"] = result
        return result

    def run_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
        debug_trace: dict[str, object] | None = None,
    ) -> AgentTurnResult:
        input_bundle = self._input_builder.build(
            session_id=session_id,
            user_message=user_message,
            context_override=context_override,
        )
        context = input_bundle.context
        graph_input = input_bundle.payload
        self._record_debug_input(debug_trace=debug_trace, graph_input=graph_input)
        result = self._invoke_graph(graph=self._graph, graph_input=graph_input, debug_trace=debug_trace)
        self._record_debug_output(debug_trace=debug_trace, result=result)
        turn_result = self._turn_builder.build(
            context=context,
            result=result,
            debug_trace=debug_trace,
        )
        self._session_recorder.persist_turn(
            session_id=session_id,
            context=context,
            user_message=user_message,
            result=result,
            turn_result=turn_result,
        )
        return turn_result

    def stream_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
        debug_trace: dict[str, object] | None = None,
    ) -> Iterator[AgentStreamEvent]:
        input_bundle = self._input_builder.build(
            session_id=session_id,
            user_message=user_message,
            context_override=context_override,
        )
        context = input_bundle.context
        graph_input = input_bundle.payload
        self._record_debug_input(debug_trace=debug_trace, graph_input=graph_input)
        yield from self._stream_orchestrator.stream(
            session_id=session_id,
            user_message=user_message,
            context=context,
            graph_input=graph_input,
            debug_trace=debug_trace,
        )

    def _record_debug_output(
        self,
        *,
        debug_trace: dict[str, object] | None,
        result: dict[str, object],
    ) -> None:
        if debug_trace is None:
            return
        query_understanding = result.get("query_understanding")
        if isinstance(query_understanding, dict):
            debug_trace.setdefault("series_query_processor", {"output": query_understanding})
        retrieval_request = result.get("retrieval_request")
        if isinstance(retrieval_request, dict):
            debug_trace.setdefault("retrieval_request", retrieval_request)
        retrieval_results = result.get("retrieval_results")
        if isinstance(retrieval_results, list):
            debug_trace.setdefault("retrieval_response", {"hits": retrieval_results})
        web_search_results = result.get("web_search_results")
        if isinstance(web_search_results, list):
            debug_trace.setdefault("web_search_response", {"hits": web_search_results})
        evidence_items = result.get("evidence_items")
        if isinstance(evidence_items, list):
            debug_trace.setdefault("evidence_items", evidence_items)
        answer_payload = result.get("answer_payload")
        if isinstance(answer_payload, dict):
            debug_trace.setdefault("answer_synthesis", {"output": answer_payload})

    def _stream_deferred_answer(
        self,
        result: dict[str, object],
    ) -> Iterator[ChatCompletionStreamChunk]:
        if self._answer_stream_gateway is None:
            raise RuntimeError("回答流式网关尚未注入。")
        raw_messages = result.get("stream_answer_messages")
        if not isinstance(raw_messages, list) or not raw_messages:
            raise ValueError("流式回答缺少 stream_answer_messages。")
        messages = [
            AgentChatMessage.model_validate(item)
            for item in raw_messages
            if isinstance(item, dict)
        ]
        if not messages:
            raise ValueError("流式回答消息为空。")
        return self._answer_stream_gateway.create_text_completion_stream_with_metadata(messages)

    def clear_session(
        self,
        *,
        session_id: str,
    ) -> None:
        self._session_recorder.clear_session(session_id)
