"""Agent 图服务的公开 API，提供回合执行与流式回答的统一入口。

本模块定义 `AgentGraphService`——将 LangGraph 图调用、回合构建、会话记录
与流式编排封装为唯一的对外调用面，供 FastAPI 路由与 SSE 端点消费。
"""

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
    """Agent 图服务的公开 API，封装 LangGraph 工作流的完整调用闭环。

    业务意图：将"构建图形输入 → 执行图 → 构建回合结果 → 持久化会话 → 流式回答"
    收敛到 `run_turn` 与 `stream_with_context` 两个公开方法，路由层无需
    感知内部编排细节。

    关键不变式：
    - 每个回合必定通过 `AgentGraphTurnBuilder` 构建结构化的 `AgentTurnResult`；
    - 每个回合必定通过 `AgentGraphSessionRecorder` 持久化到会话存储；
    - 流式路径与非流式路径共享同一套回合构建与会话记录逻辑；
    - `answer_stream_gateway` 为 `None` 时走图内文本切分流式兜底。
    """
    def __init__(
        self,
        *,
        context_loader: AgentContextLoader,
        graph,
        session_store=None,
        memory_compactor: MemoryMessageCompactor | None = None,
        answer_stream_gateway: ChatGateway | None = None,
    ) -> None:
        """注入图实例、上下文加载器、会话存储等依赖。

        Args:
            context_loader: 从会话 ID 加载 `AgentContext` 的端口。
            graph: 已编译的 LangGraph StateGraph 实例（含节点与路由）。
            session_store: 可选的会话持久化端口；为 `None` 时不记录多轮历史。
            memory_compactor: 可选的消息压缩器，在会话记录后触发压缩；为 `None`
                时不压缩。
            answer_stream_gateway: 可选的 LLM 流式网关，用于延迟流式回答场景；
                为 `None` 时流式路径走图内文本切分兜底。
        """
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
        """将图输入摘要写入 debug_trace（若提供）。

        Args:
            debug_trace: 外部传入的调试字典；为 `None` 时跳过。
            graph_input: 即将送入图的完整状态字典。
        """
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
        """同步调用 LangGraph 图并返回最终状态。

        Args:
            graph: 已编译的 LangGraph StateGraph 实例。
            graph_input: 图的初始状态负载。
            debug_trace: 为 `None` 时跳过调试记录。

        Returns:
            图运行结束后的最终状态字典。
        """
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
        """执行一次对话回合（非流式），返回结构化的 `AgentTurnResult`。

        完整的调用链路：
        1. 通过 `AgentGraphInputBuilder` 构建图输入与 AgentContext；
        2. 同步调用 LangGraph 图；
        3. 通过 `AgentGraphTurnBuilder` 从图输出构建 `AgentTurnResult`；
        4. 通过 `AgentGraphSessionRecorder` 持久化本轮对话。

        Args:
            session_id: 会话唯一 ID。
            user_message: 用户最新问题原文。
            context_override: 可选的 `AgentContext` 覆盖值；为 `None` 时从
                session_store 自动加载。
            debug_trace: 可选的调试信息收集字典；为 `None` 时不记录。

        Returns:
            结构化的 `AgentTurnResult`，包含助手消息、工具结果与引用。
        """
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
        """执行一次对话回合并以 `AgentStreamEvent` 迭代器流式返回结果。

        与 `run_turn` 的区别：本方法通过 `AgentGraphStreamOrchestrator` 将
        图执行过程拆解为 `thinking_started`、`stage_started`、`stage_completed`、
        `tool_completed`、`answer_delta`、`answer_completed` 等 SSE 事件，
        供前端实时渲染每一步进展。

        Args:
            session_id: 会话唯一 ID。
            user_message: 用户最新问题原文。
            context_override: 可选的 `AgentContext` 覆盖值；为 `None` 时自动加载。
            debug_trace: 可选的调试信息收集字典；为 `None` 时不记录。

        Yields:
            `AgentStreamEvent` 序列，按时间顺序描述图执行的各阶段。
        """
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
        """将图输出中的结构化字段写入 debug_trace（若提供）。

        自动提取 query_understanding、retrieval_request、retrieval_results、
        web_search_results、evidence_items、answer_payload 等中间产物并分类归入
        debug_trace 对应键下。

        Args:
            debug_trace: 外部传入的调试字典；为 `None` 时跳过。
            result: 图运行结束后的最终状态字典。
        """
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
        """将图结果中的延迟回答消息通过流式网关转为 `ChatCompletionStreamChunk`。

        仅在 `answer_stream_gateway` 已注入且图结果包含 `stream_answer_messages`
        时可用；典型场景是 LLM 规划了工具调用但回答被推迟到工具执行完毕后流式生成。

        Args:
            result: 图运行结束后的最终状态字典，必须含 `stream_answer_messages`。

        Returns:
            `ChatCompletionStreamChunk` 迭代器。

        Raises:
            RuntimeError: answer_stream_gateway 未注入。
            ValueError: result 中缺少有效的 stream_answer_messages。
        """
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
        """清除指定会话的全部历史记录。

        Args:
            session_id: 目标会话 ID。
        """
        self._session_recorder.clear_session(session_id)
