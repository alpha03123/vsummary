"""Agent 图的流式编排模块，将图执行过程拆解为前端可渲染的 SSE 事件。

本模块定义 `AgentGraphStreamOrchestrator`——监听 LangGraph 的 debug 模式
事件流，将其映射为 `thinking_started`、`stage_started`、`stage_completed`、
`tool_completed`、`answer_delta`、`answer_completed` 等 `AgentStreamEvent`，
并处理行内引用解析与延迟流式回答。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

from backend.agent.schemas.chat_stream import ChatCompletionStreamChunk
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent_graph.evidence.inline_citations import filter_inline_citation_markers, resolve_inline_citations
from backend.agent_graph.evidence.transcript_anchors import number_evidence_items_for_citations
from backend.agent_graph.runtime.node_catalog import get_node_alias
from backend.agent_graph.runtime.outcome import extract_assistant_message, extract_tool_results


class AgentGraphStreamOrchestrator:
    """Agent 图流式编排器，将 LangGraph 执行过程转为 SSE 事件流。

    业务意图：前端需要实时看到 Agent 推理/检索/工具调用/回答生成的每一步进展，
    本编排器通过 LangGraph 的 `stream_mode="debug"` 监听每个节点的起止与产出，
    转换为统一的 `AgentStreamEvent` 序列供 SSE 端点消费。

    关键不变式：
    - 总是以 `thinking_started` 开头、`thinking_completed` 结尾；
    - 工具调用结果按发现顺序递增编号（`tool-1`、`tool-2`...）；
    - 非流式回答按标点/长度切分为 `answer_delta` 分片；
    - 流式回答（deferred）在工具链完成后通过 LLM 网关异步生成，并解析行内引用；
    - 无论走哪条路径，最终都会通过 `session_recorder` 持久化本回合。
    """
    def __init__(
        self,
        *,
        graph,
        invoke_graph: Callable[..., dict[str, object]],
        turn_builder,
        session_recorder,
        answer_streamer: Callable[[dict[str, object]], Iterator[ChatCompletionStreamChunk]] | None = None,
    ) -> None:
        """注入图实例、调用回调、回合构建器与可选延迟流式网关。

        Args:
            graph: 已编译的 LangGraph StateGraph 实例。
            invoke_graph: 同步调用图的回调（通常由 `AgentGraphService` 提供）。
            turn_builder: 用于从图输出构建 `AgentTurnResult` 的建造者。
            session_recorder: 用于在流式结束后持久化回合的会话记录器。
            answer_streamer: 可选的 LLM 流式回答回调，用于延迟流式场景；
                为 `None` 时走图内文本切分流式兜底。
        """
        self._graph = graph
        self._invoke_graph = invoke_graph
        self._turn_builder = turn_builder
        self._session_recorder = session_recorder
        self._answer_streamer = answer_streamer

    def stream(
        self,
        *,
        session_id: str,
        user_message: str,
        context,
        graph_input: dict[str, object],
        debug_trace: dict[str, object] | None = None,
    ) -> Iterator[AgentStreamEvent]:
        """编排一次流式回合，产出 `AgentStreamEvent` 迭代器。

        两条路径：
        - **图不支持 debug 流式**：走同步 invoke → 切分回答文本 → 逐片产出；
        - **图支持 debug 流式**：监听 `task`/`task_result` debug 事件，
          映射 node 起止、工具调用结果，最终流式或切分回答。

        流式事件类型与触发时机：
        - `thinking_started`：回合开始；
        - `stage_started`：节点开始执行（含 node_id 与中文别名）；
        - `stage_completed`：节点执行完成（含耗时 ms）；
        - `tool_completed`：单个工具调用完成（含工具名、状态与负载）；
        - `tool_chain_completed`：当前阶段全部工具调用完成；
        - `answer_started`：开始生成回答；
        - `answer_delta`：回答文本分片；
        - `answer_completed`：回答结束（含全文、引用与耗时）；
        - `thinking_completed`：回合结束。

        Args:
            session_id: 会话唯一 ID。
            user_message: 用户最新问题原文。
            context: 当前会话的 `AgentContext`。
            graph_input: 图的初始状态负载。
            debug_trace: 可选的调试信息收集字典；为 `None` 时不记录。

        Yields:
            `AgentStreamEvent` 序列，按执行时间顺序。
        """
        graph_input = _with_deferred_answer(graph_input, self._answer_streamer is not None)

        if not hasattr(self._graph, "stream"):
            result = self._invoke_graph(
                graph=self._graph,
                graph_input=graph_input,
                debug_trace=debug_trace,
            )
            if self._has_deferred_answer(result):
                yield from self._stream_deferred_answer_result(
                    result=result,
                    session_id=session_id,
                    user_message=user_message,
                    context=context,
                    stream_started_at=None,
                    debug_trace=debug_trace,
                )
                return
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

        if self._has_deferred_answer(result):
            yield from self._stream_deferred_answer_result(
                result=result,
                session_id=session_id,
                user_message=user_message,
                context=context,
                stream_started_at=stream_started_at,
                debug_trace=debug_trace,
            )
            return

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
        available_citation_ids = {item.id for item in turn_result.citations}
        assistant_message = filter_inline_citation_markers(
            turn_result.assistant_message,
            available_citation_ids,
        )
        if assistant_message != turn_result.assistant_message:
            result = {
                **result,
                "answer": assistant_message,
                "assistant_message": assistant_message,
            }
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

    def _has_deferred_answer(self, result: dict[str, object]) -> bool:
        """判断图结果是否包含需要延迟流式输出的回答消息。

        Returns:
            `True` 当且仅当 answer_streamer 已注入且结果中含 `stream_answer_messages`。
        """
        return self._answer_streamer is not None and isinstance(result.get("stream_answer_messages"), list)

    def _stream_deferred_answer_result(
        self,
        *,
        result: dict[str, object],
        session_id: str,
        user_message: str,
        context,
        stream_started_at: datetime | None,
        debug_trace: dict[str, object] | None,
        emitted_tool_count: int = 0,
    ) -> Iterator[AgentStreamEvent]:
        """处理延迟流式回答路径：通过 LLM 网关生成流式回答并解析行内引用。

        与图内切分回答的区别：本方法调用 `answer_streamer` 让 LLM 真正流式
        生成每个 token，同时对回答文本做行内引用解析（将 [1],[2] 等标记替换
        为实际引用），最后持久化回合并产出 `answer_completed` 事件。

        Args:
            result: 图运行结束后的状态字典。
            session_id: 会话唯一 ID。
            user_message: 用户最新问题原文。
            context: 当前会话的 `AgentContext`。
            stream_started_at: 流式开始时间戳；为 `None` 时后续用 `datetime.now()`。
            debug_trace: 可选的调试字典；为 `None` 时不记录。
            emitted_tool_count: 已产出的工具调用数量（默认 0）。

        Yields:
            `answer_delta`、`thinking_completed`、`answer_completed` 等 SSE 事件。

        Raises:
            RuntimeError: answer_streamer 未注入或 LLM 流式回答为空。
        """
        if self._answer_streamer is None:
            raise RuntimeError("回答流式生成器尚未注入。")
        if emitted_tool_count:
            yield AgentStreamEvent(
                type="tool_chain_completed",
                payload={
                    "count": emitted_tool_count,
                    "duration_ms": _sum_tool_durations(extract_tool_results(result)),
                },
            )
        yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
        answer_parts: list[str] = []
        answer_usage: dict[str, int] = {}
        for chunk in self._answer_streamer(result):
            if chunk.usage:
                answer_usage = dict(chunk.usage)
            if chunk.delta:
                answer_parts.append(chunk.delta)
                yield AgentStreamEvent(type="answer_delta", payload={"delta": chunk.delta})
        assistant_message = "".join(answer_parts).strip()
        if not assistant_message:
            raise RuntimeError("模型流式回答为空。")
        citation_resolution = resolve_inline_citations(
            assistant_message,
            _graph_evidence_items(result),
        )
        assistant_message = citation_resolution.answer_text
        used_evidence_ids = citation_resolution.used_evidence_ids
        used_citation_ids = citation_resolution.used_citation_ids

        stream_finished_at = _current_time_like(stream_started_at)
        result = {
            **result,
            "answer": assistant_message,
            "assistant_message": assistant_message,
            "used_evidence_ids": used_evidence_ids,
            "used_citation_ids": used_citation_ids,
        }
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
    """将 LangGraph debug 事件的时间戳字符串解析为 `datetime`。

    Args:
        value: 原始时间戳值；非空字符串视为 ISO 格式，否则返回 `None`。

    Returns:
        解析后的 `datetime`，无法解析时返回 `None`。
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value)


def _with_deferred_answer(graph_input: dict[str, object], enabled: bool) -> dict[str, object]:
    """为图输入标记"延迟流式回答"标志，告知图节点不要内联生成回答文本。

    Args:
        graph_input: 图的初始状态字典。
        enabled: 是否启用延迟流式回答模式。

    Returns:
        若 enabled 则返回含 `defer_answer_stream=True` 的副本；否则原样返回。
    """
    if not enabled:
        return graph_input
    return {
        **graph_input,
        "defer_answer_stream": True,
    }


def _graph_evidence_items(result: dict[str, object]) -> list[dict[str, object]]:
    """从图结果中提取 evidence_items，回退到 retrieval_results。

    用于行内引用解析时获取可引用的证据条目列表。

    Args:
        result: 图运行结束后的状态字典。

    Returns:
        dict 类型的证据条目列表；无有效数据时返回空列表。
    """
    raw_items = result.get("evidence_items", result.get("retrieval_results", []))
    if not isinstance(raw_items, list):
        return []
    evidence_items = [item for item in raw_items if isinstance(item, dict)]
    return number_evidence_items_for_citations(evidence_items)


def _duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    """计算两个时间戳之间的毫秒差值。

    Args:
        start: 起始时间戳；为 `None` 则返回 `None`。
        end: 结束时间戳；为 `None` 则返回 `None`。

    Returns:
        非负毫秒差值；任一参数为 `None` 时返回 `None`。
    """
    if start is None or end is None:
        return None
    delta_ms = int((end - start).total_seconds() * 1000)
    return max(delta_ms, 0)


def _current_time_like(reference: datetime | None) -> datetime:
    """获取当前时间，时区与参考时间戳保持一致。

    Args:
        reference: 参考时间戳；为 `None` 或无时区信息时使用本地时间。

    Returns:
        当前 `datetime`，时区与 reference 对齐。
    """
    if reference is None or reference.tzinfo is None:
        return datetime.now()
    return datetime.now(tz=reference.tzinfo)


def _build_tool_completed_event(tool_result, *, index: int) -> AgentStreamEvent:
    """将工具调用结果组装为 `tool_completed` 类型的 `AgentStreamEvent`。

    Args:
        tool_result: 工具调用的结果对象，含 `payload`、`tool_name`、`status`。
        index: 工具调用序号（从 1 开始）。

    Returns:
        填充了 `tool_call_id`、`tool_name`、`status`、`index`、`payload` 与
        `duration_ms` 的 `AgentStreamEvent`。
    """
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
    """累加所有工具调用结果的耗时（ms）。

    Args:
        tool_results: 工具调用结果列表，每个含 `payload.duration_ms`。

    Returns:
        累计毫秒数；无有效 duration 时返回 `None`。
    """
    durations = [
        int(item.payload.get("duration_ms"))
        for item in tool_results
        if isinstance(item.payload, dict) and isinstance(item.payload.get("duration_ms"), int)
    ]
    if not durations:
        return None
    return sum(durations)


def _chunk_text(text: str, *, max_chars: int = 24) -> Iterator[str]:
    """将文本按标点或长度切分为流式输出分片（模拟 LLM token 级流式）。

    用于图不支持 debug 流式或 answer_streamer 未注入时，将完整回答文本切分
    为 `answer_delta` 事件。

    Args:
        text: 待切分的完整文本。
        max_chars: 单个分片的最大字符数（默认 24）。

    Yields:
        逐个文本分片。
    """
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
