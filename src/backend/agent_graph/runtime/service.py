from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from backend.agent.ports import AgentContextLoader
from backend.agent.memory.dialog_history import DialogHistoryCompactor, render_dialog_history
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult, ScopeType
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName
from backend.agent.session.models import AgentSessionSelectedVideoEntry
from backend.agent_graph.evidence.citations import build_citations_from_graph_result
from backend.agent_graph.runtime.node_catalog import get_node_alias
from backend.agent_graph.runtime.nodes import (
    append_answer_to_state,
    apply_memory_update,
    finalize_state,
    should_use_series_aggregator,
)


class AgentGraphService:
    def __init__(
        self,
        *,
        context_loader: AgentContextLoader,
        graph,
        session_store=None,
        decomposer_program=None,
        classifier_program=None,
        compare_split_program=None,
        series_planner=None,
        retrieval_service=None,
        pinpoint_service=None,
        meta_state_reader=None,
        action_dispatcher=None,
        answer_program=None,
        series_aggregator=None,
        memory_update_program=None,
        dialog_history_compactor: DialogHistoryCompactor | None = None,
        dialog_history_window_tokens: int = 1_000_000,
        dialog_history_compression_ratio: float = 0.90,
    ) -> None:
        self._context_loader = context_loader
        self._graph = graph
        self._session_store = session_store
        self._decomposer_program = decomposer_program
        self._classifier_program = classifier_program
        self._compare_split_program = compare_split_program
        self._series_planner = series_planner
        self._retrieval_service = retrieval_service
        self._pinpoint_service = pinpoint_service
        self._meta_state_reader = meta_state_reader
        self._action_dispatcher = action_dispatcher
        self._answer_program = answer_program
        self._series_aggregator = series_aggregator
        self._memory_update_program = memory_update_program
        self._dialog_history_compactor = dialog_history_compactor
        self._dialog_history_window_tokens = dialog_history_window_tokens
        self._dialog_history_compression_ratio = dialog_history_compression_ratio

    @property
    def graph(self):
        return self._graph

    def _build_graph_input(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
    ) -> tuple[object, dict[str, object]]:
        context = context_override or self._context_loader.load(session_id)
        history_messages: list[dict[str, object]] = []
        dialog_history = str(getattr(context, "dialog_history", "") or "").strip()
        evidence_history = dict(getattr(context, "evidence_history", {}) or {})
        history_selected_videos: list[dict[str, object]] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                history_messages = [
                    {"role": item.role, "content": item.content}
                    for item in snapshot.messages
                ]
                dialog_history = str(getattr(snapshot.context, "dialog_history", "") or "").strip()
                evidence_history = dict(getattr(snapshot.context, "evidence_history", {}) or {})
                history_selected_videos = [
                    {
                        "video_id": item.video_id,
                        "reason_for_selection": item.reason_for_selection,
                    }
                    for item in snapshot.selected_videos
                ]
        graph_input = {
            "session_id": session_id,
            "scope_type": context.scope_type,
            "series_id": context.series_id or "",
            "video_id": context.video_id or "",
            "user_message": user_message,
            "dialog_history": dialog_history,
            "evidence_history": evidence_history,
            "history_messages": history_messages,
            "history_summary": dialog_history,
            "history_selected_videos": history_selected_videos,
        }
        return context, graph_input

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
        graph_input: dict[str, object],
        debug_trace: dict[str, object] | None = None,
    ) -> dict[str, object]:
        result = self._graph.invoke(graph_input)
        if debug_trace is not None:
            debug_trace["graph_result"] = result
        return result

    def _build_turn_result(
        self,
        *,
        context,
        result: dict[str, object],
        debug_trace: dict[str, object] | None = None,
    ) -> AgentTurnResult:
        assistant_message = str(
            result.get("assistant_message")
            or result.get("direct_response")
            or result.get("answer", "")
        ).strip()
        tool_results = _build_tool_results(result)
        citations = build_citations_from_graph_result(result)
        turn_result = AgentTurnResult(
            assistant_message=assistant_message,
            plan=AgentActionPlan(
                scope_type=ScopeType(context.scope_type),
                tool_calls=[],
                reason=str(result.get("query_plan", {})),
                direct_response=str(result.get("direct_response", "")),
                use_answerer=not bool(result.get("direct_response")),
            ),
            tool_results=tool_results,
            citations=citations,
        )
        if debug_trace is not None:
            debug_trace["assistant_message"] = assistant_message
            debug_trace["tool_results"] = [item.model_dump(mode="json") for item in tool_results]
            debug_trace["citations"] = [item.model_dump(mode="json") for item in citations]
            debug_trace["turn_result"] = {
                "assistant_message": assistant_message,
                "reason": turn_result.plan.reason,
            }
        return turn_result

    def _persist_turn(
        self,
        *,
        session_id: str,
        context,
        user_message: str,
        result: dict[str, object],
        turn_result: AgentTurnResult,
    ) -> None:
        if self._session_store is None:
            return
        dialog_history = self._build_next_dialog_history(
            session_id=session_id,
            user_message=user_message,
            assistant_message=turn_result.assistant_message,
        )
        persisted_context = context.model_copy(
            update={
                "dialog_history": dialog_history,
                "evidence_history": _merge_evidence_history(
                    current=dict(getattr(context, "evidence_history", {}) or {}),
                    result=result,
                ),
            }
        )
        self._session_store.append_turn(
            session_id=session_id,
            memory_key=session_id,
            context=persisted_context,
            user_message=user_message,
            assistant_message=turn_result.assistant_message,
            tool_results=turn_result.tool_results,
            selected_videos=[
                AgentSessionSelectedVideoEntry(
                    video_id=str(item.get("video_id", "")).strip(),
                    reason_for_selection=str(item.get("reason_for_selection", "")).strip(),
                )
                for item in _extract_selected_videos(result)
                if str(item.get("video_id", "")).strip()
            ],
        )

    def _build_next_dialog_history(
        self,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> str:
        messages: list[AgentChatMessage] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                messages.extend(
                    AgentChatMessage(role=item.role, content=item.content)
                    for item in snapshot.messages
                )
        messages.extend(
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=assistant_message),
            ]
        )
        if self._dialog_history_compactor is not None:
            return self._dialog_history_compactor.compact_if_needed(messages)
        return render_dialog_history(messages)

    def run_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
        debug_trace: dict[str, object] | None = None,
    ) -> AgentTurnResult:
        return self.run_turn(
            session_id=session_id,
            user_message=user_message,
            context_override=context_override,
            debug_trace=debug_trace,
        )

    def run(self, session_id: str, user_message: str) -> AgentTurnResult:  # type: ignore[override]
        return self.run_turn(session_id=session_id, user_message=user_message)

    def run_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
        debug_trace: dict[str, object] | None = None,
    ) -> AgentTurnResult:
        context, graph_input = self._build_graph_input(
            session_id=session_id,
            user_message=user_message,
            context_override=context_override,
        )
        self._record_debug_input(debug_trace=debug_trace, graph_input=graph_input)
        result = self._invoke_graph(graph_input=graph_input, debug_trace=debug_trace)
        turn_result = self._build_turn_result(
            context=context,
            result=result,
            debug_trace=debug_trace,
        )
        self._persist_turn(
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
        context, graph_input = self._build_graph_input(
            session_id=session_id,
            user_message=user_message,
            context_override=context_override,
        )
        self._record_debug_input(debug_trace=debug_trace, graph_input=graph_input)

        if not hasattr(self._graph, "stream"):
            turn_result = self.run_turn(
                session_id=session_id,
                user_message=user_message,
                context_override=context,
                debug_trace=debug_trace,
            )
            yield AgentStreamEvent(type="thinking_started", payload={"message": "正在执行图节点"})
            yield AgentStreamEvent(type="thinking_completed", payload={})
            if turn_result.tool_results:
                for index, tool_result in enumerate(turn_result.tool_results, start=1):
                    yield _build_tool_completed_event(tool_result, index=index)
                yield AgentStreamEvent(
                    type="tool_chain_completed",
                    payload={"count": len(turn_result.tool_results)},
                )
            yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
            for delta in _chunk_text(turn_result.assistant_message):
                yield AgentStreamEvent(type="answer_delta", payload={"delta": delta})
            yield AgentStreamEvent(
                type="answer_completed",
                payload={"message": turn_result.assistant_message},
            )
            return

        raw_debug_events: list[dict[str, object]] = []
        emitted_tool_count = 0
        stage_started_at: dict[str, datetime] = {}
        stream_started_at: datetime | None = None
        stream_finished_at: datetime | None = None
        final_result: dict[str, object] | None = None
        answer_usage: dict[str, int] = {}

        interrupt_before = ["answer"] if self._series_aggregator is not None else None

        yield AgentStreamEvent(type="thinking_started", payload={"message": "正在执行图节点"})

        for raw_event in self._graph.stream(
            graph_input,
            stream_mode="debug",
            interrupt_before=interrupt_before,
        ):
            if not isinstance(raw_event, dict):
                continue
            raw_debug_events.append(raw_event)
            event_timestamp = _parse_timestamp(raw_event.get("timestamp"))
            if stream_started_at is None and event_timestamp is not None:
                stream_started_at = event_timestamp
            if event_timestamp is not None:
                stream_finished_at = event_timestamp

            event_type = str(raw_event.get("type", "")).strip()
            payload = raw_event.get("payload", {})
            if not isinstance(payload, dict):
                continue

            if event_type == "task":
                stage_id = str(payload.get("id", "")).strip()
                node_id = str(payload.get("name", "")).strip()
                if not stage_id or not node_id:
                    continue
                if event_timestamp is not None:
                    stage_started_at[stage_id] = event_timestamp
                yield AgentStreamEvent(
                    type="stage_started",
                    payload={
                        "stage_id": stage_id,
                        "node_id": node_id,
                        "label": get_node_alias(node_id),
                    },
                )
                continue

            if event_type != "task_result":
                continue

            stage_id = str(payload.get("id", "")).strip()
            node_id = str(payload.get("name", "")).strip()
            result = payload.get("result")
            if isinstance(result, dict):
                final_result = result
                current_tool_results = _build_tool_results(result)
                new_tool_results = current_tool_results[emitted_tool_count:]
                for index, tool_result in enumerate(new_tool_results, start=emitted_tool_count + 1):
                    yield _build_tool_completed_event(tool_result, index=index)
                emitted_tool_count += len(new_tool_results)

            duration_ms = _duration_ms(stage_started_at.get(stage_id), event_timestamp)
            yield AgentStreamEvent(
                type="stage_completed",
                payload={
                    "stage_id": stage_id,
                    "node_id": node_id,
                    "label": get_node_alias(node_id),
                    "duration_ms": duration_ms,
                },
            )

        if debug_trace is not None:
            debug_trace["graph_stream_debug"] = raw_debug_events

        result = final_result or self._invoke_graph(graph_input=graph_input, debug_trace=debug_trace)
        should_stream_answer = (
            isinstance(result, dict)
            and not str(result.get("assistant_message", "")).strip()
            and should_use_series_aggregator(result, self._series_aggregator)
        )

        if emitted_tool_count:
            yield AgentStreamEvent(
                type="tool_chain_completed",
                payload={
                    "count": emitted_tool_count,
                    "duration_ms": _sum_tool_durations(_build_tool_results(result)),
                },
            )

        if should_stream_answer:
            answer_stage_id = "stage-answer"
            answer_started_at = _current_time_like(stream_started_at)
            stage_started_at[answer_stage_id] = answer_started_at
            yield AgentStreamEvent(
                type="stage_started",
                payload={
                    "stage_id": answer_stage_id,
                    "node_id": "answer",
                    "label": get_node_alias("answer"),
                },
            )
            yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})

            answer_text = ""
            for chunk in self._series_aggregator.stream(
                user_message=result["user_message"],
                query_plan=dict(result.get("query_plan", {})),
                execution_results=list(result.get("retrieval_results", [])),
                tool_results=list(result.get("tool_results", [])),
                dialog_history=str(result.get("dialog_history", "")),
                history_messages=list(result.get("history_messages", [])),
                debug_trace=debug_trace,
            ):
                if chunk.delta:
                    answer_text += chunk.delta
                    yield AgentStreamEvent(type="answer_delta", payload={"delta": chunk.delta})
                if chunk.usage:
                    answer_usage = dict(chunk.usage)
            answer_finished_at = _current_time_like(answer_started_at)
            yield AgentStreamEvent(
                type="stage_completed",
                payload={
                    "stage_id": answer_stage_id,
                    "node_id": "answer",
                    "label": get_node_alias("answer"),
                    "duration_ms": _duration_ms(answer_started_at, answer_finished_at),
                },
            )

            result = append_answer_to_state(result, answer_text)

            finalize_started_at = _current_time_like(answer_finished_at)
            yield AgentStreamEvent(
                type="stage_started",
                payload={
                    "stage_id": "stage-finalize",
                    "node_id": "finalize",
                    "label": get_node_alias("finalize"),
                },
            )
            result = finalize_state(result)
            finalize_finished_at = _current_time_like(finalize_started_at)
            yield AgentStreamEvent(
                type="stage_completed",
                payload={
                    "stage_id": "stage-finalize",
                    "node_id": "finalize",
                    "label": get_node_alias("finalize"),
                    "duration_ms": _duration_ms(finalize_started_at, finalize_finished_at),
                },
            )

            if self._memory_update_program is not None:
                memory_started_at = _current_time_like(finalize_finished_at)
                yield AgentStreamEvent(
                    type="stage_started",
                    payload={
                        "stage_id": "stage-update-memory",
                        "node_id": "update_memory",
                        "label": get_node_alias("update_memory"),
                    },
                )
                result = apply_memory_update(result, memory_update_program=self._memory_update_program)
                stream_finished_at = _current_time_like(memory_started_at)
                yield AgentStreamEvent(
                    type="stage_completed",
                    payload={
                        "stage_id": "stage-update-memory",
                        "node_id": "update_memory",
                        "label": get_node_alias("update_memory"),
                        "duration_ms": _duration_ms(memory_started_at, stream_finished_at),
                    },
                )
            else:
                stream_finished_at = finalize_finished_at
        else:
            if not str(result.get("assistant_message", "")).strip():
                if debug_trace is not None:
                    debug_trace["graph_result"] = result
                result = self._invoke_graph(graph_input=graph_input, debug_trace=debug_trace)
            yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
            assistant_message = str(
                result.get("assistant_message")
                or result.get("direct_response")
                or result.get("answer", "")
            ).strip()
            for delta in _chunk_text(assistant_message):
                yield AgentStreamEvent(type="answer_delta", payload={"delta": delta})

        if debug_trace is not None:
            debug_trace["graph_result"] = result
            if answer_usage:
                debug_trace["answer_stream_usage"] = answer_usage

        turn_result = self._build_turn_result(
            context=context,
            result=result,
            debug_trace=debug_trace,
        )
        self._persist_turn(
            session_id=session_id,
            context=context,
            user_message=user_message,
            result=result,
            turn_result=turn_result,
        )

        total_duration_ms = _duration_ms(stream_started_at, stream_finished_at)
        yield AgentStreamEvent(
            type="thinking_completed",
            payload={"duration_ms": total_duration_ms},
        )
        answer_completed_payload: dict[str, object] = {
            "message": turn_result.assistant_message,
            "duration_ms": total_duration_ms,
        }
        if answer_usage:
            answer_completed_payload["usage"] = answer_usage
        yield AgentStreamEvent(
            type="answer_completed",
            payload=answer_completed_payload,
        )

    def clear_session(
        self,
        *,
        session_id: str,
        context_override=None,
    ) -> None:
        if self._session_store is not None:
            self._session_store.clear_snapshot(session_id)


class SeriesAgentGraphService(AgentGraphService):
    pass


def _build_tool_results(result: dict[str, object]) -> list[ToolExecutionResult]:
    explicit_tool_results = result.get("tool_results")
    if isinstance(explicit_tool_results, list) and explicit_tool_results:
        normalized: list[ToolExecutionResult] = []
        for item in explicit_tool_results:
            if not isinstance(item, dict):
                continue
            normalized.append(
                ToolExecutionResult(
                    tool_name=ToolName(str(item.get("tool_name"))),
                    status=str(item.get("status", "ok")),
                    payload=dict(item.get("payload", {})) if isinstance(item.get("payload", {}), dict) else {},
                )
            )
        if normalized:
            return normalized
    retrieval_results = result.get("retrieval_results", [])
    if not isinstance(retrieval_results, list) or not retrieval_results:
        return []
    first = retrieval_results[0]
    if not isinstance(first, dict):
        return []
    source_type = str(first.get("source_type", "summary"))
    tool_name = ToolName.GET_VIDEO_TRANSCRIPT if source_type == "transcript_chunk" else ToolName.GET_VIDEO_SUMMARY
    return [
        ToolExecutionResult(
            tool_name=tool_name,
            status="ok",
            payload={"graph_result": True, "result_count": len(retrieval_results)},
        )
    ]


def _extract_selected_videos(result: dict[str, object]):
    query_plan = result.get("query_plan", {})
    if not isinstance(query_plan, dict):
        return []
    selected_videos = query_plan.get("selected_videos", [])
    if not isinstance(selected_videos, list):
        return []
    return [item for item in selected_videos if isinstance(item, dict) and str(item.get("video_id", "")).strip()]


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value)


def _duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    delta_ms = int((end - start).total_seconds() * 1000)
    return max(delta_ms, 0)


def _current_time_like(reference: datetime | None) -> datetime:
    if reference is None or reference.tzinfo is None:
        return datetime.now()
    return datetime.now(tz=reference.tzinfo)


def _build_tool_completed_event(tool_result: ToolExecutionResult, *, index: int) -> AgentStreamEvent:
    payload = dict(tool_result.payload)
    return AgentStreamEvent(
        type="tool_completed",
        payload={
            "tool_call_id": f"tool-{index}",
            "tool_name": tool_result.tool_name.value,
            "status": tool_result.status,
            "index": index,
            "payload": payload,
            "duration_ms": payload.get("duration_ms") if isinstance(payload.get("duration_ms"), int) else None,
        },
    )


def _sum_tool_durations(tool_results: list[ToolExecutionResult]) -> int | None:
    durations = [
        int(item.payload.get("duration_ms"))
        for item in tool_results
        if isinstance(item.payload, dict) and isinstance(item.payload.get("duration_ms"), int)
    ]
    if not durations:
        return None
    return sum(durations)


def _chunk_text(text: str, *, max_chars: int = 24) -> Iterator[str]:
    if not text:
        return
    buffer = ""
    delimiters = {"\n", "。", "！", "？", "；", "：", "，", ",", ".", "!", "?", ";", ":"}
    for char in text:
        buffer += char
        if char in delimiters or len(buffer) >= max_chars:
            yield buffer
            buffer = ""
    if buffer:
        yield buffer


def _merge_evidence_history(*, current: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    merged = dict(current)
    evidence_history = result.get("evidence_history", {})
    if isinstance(evidence_history, dict):
        merged.update(evidence_history)
    return merged
