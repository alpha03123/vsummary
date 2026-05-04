from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent_graph.runtime.node_catalog import get_node_alias
from backend.agent_graph.runtime.outcome import extract_assistant_message, extract_tool_results


class AgentGraphStreamOrchestrator:
    def __init__(
        self,
        *,
        graph,
        invoke_graph: Callable[..., dict[str, object]],
        turn_builder,
        session_recorder,
    ) -> None:
        self._graph = graph
        self._invoke_graph = invoke_graph
        self._turn_builder = turn_builder
        self._session_recorder = session_recorder

    def stream(
        self,
        *,
        session_id: str,
        user_message: str,
        context,
        graph_input: dict[str, object],
        debug_trace: dict[str, object] | None = None,
    ) -> Iterator[AgentStreamEvent]:
        if not hasattr(self._graph, "stream"):
            result = self._invoke_graph(
                graph=self._graph,
                graph_input=graph_input,
                debug_trace=debug_trace,
            )
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

        yield AgentStreamEvent(type="thinking_started", payload={"message": "正在执行图节点"})

        for raw_event in self._graph.stream(
            graph_input,
            stream_mode="debug",
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
                current_tool_results = extract_tool_results(result)
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

        result = final_result or self._invoke_graph(
            graph=self._graph,
            graph_input=graph_input,
            debug_trace=debug_trace,
        )
        if emitted_tool_count:
            yield AgentStreamEvent(
                type="tool_chain_completed",
                payload={
                    "count": emitted_tool_count,
                    "duration_ms": _sum_tool_durations(extract_tool_results(result)),
                },
            )

        if not str(result.get("assistant_message", "")).strip():
            if debug_trace is not None:
                debug_trace["graph_result"] = result
            result = self._invoke_graph(
                graph=self._graph,
                graph_input=graph_input,
                debug_trace=debug_trace,
            )
        yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
        assistant_message = extract_assistant_message(result)
        for delta in _chunk_text(assistant_message):
            yield AgentStreamEvent(type="answer_delta", payload={"delta": delta})
        stream_finished_at = _current_time_like(stream_started_at)

        if debug_trace is not None:
            debug_trace["graph_result"] = result
            if answer_usage:
                debug_trace["answer_stream_usage"] = answer_usage

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

        total_duration_ms = _duration_ms(stream_started_at, stream_finished_at)
        yield AgentStreamEvent(
            type="thinking_completed",
            payload={"duration_ms": total_duration_ms},
        )
        answer_completed_payload: dict[str, object] = {
            "message": turn_result.assistant_message,
            "duration_ms": total_duration_ms,
            "citations": [item.model_dump(mode="json") for item in turn_result.citations],
        }
        if answer_usage:
            answer_completed_payload["usage"] = answer_usage
        yield AgentStreamEvent(
            type="answer_completed",
            payload=answer_completed_payload,
        )


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


def _build_tool_completed_event(tool_result, *, index: int) -> AgentStreamEvent:
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


def _sum_tool_durations(tool_results) -> int | None:
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
