from __future__ import annotations

from collections.abc import Iterator

from backend.agent.memory.dialog_history import DialogHistoryCompactor
from backend.agent.ports import AgentContextLoader
from backend.agent.schemas.action_plan import AgentTurnResult
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
        series_aggregator=None,
        dialog_history_compactor: DialogHistoryCompactor | None = None,
    ) -> None:
        self._graph = graph
        self._series_aggregator = series_aggregator
        self._input_builder = AgentGraphInputBuilder(
            context_loader=context_loader,
            session_store=session_store,
        )
        self._turn_builder = AgentGraphTurnBuilder()
        self._session_recorder = AgentGraphSessionRecorder(
            session_store=session_store,
            dialog_history_compactor=dialog_history_compactor,
        )
        self._stream_orchestrator = AgentGraphStreamOrchestrator(
            graph=graph,
            invoke_graph=self._invoke_graph,
            turn_builder=self._turn_builder,
            session_recorder=self._session_recorder,
            series_aggregator=series_aggregator,
        )

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
            "dialog_history_tokens": len(str(graph_input.get("dialog_history", "") or "")),
            "history_message_count": len(graph_input["history_messages"]),
            "dialog_history": graph_input["dialog_history"],
            "evidence_history": graph_input["evidence_history"],
            "history_selected_videos": graph_input["history_selected_videos"],
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

    def clear_session(
        self,
        *,
        session_id: str,
    ) -> None:
        self._session_recorder.clear_session(session_id)
