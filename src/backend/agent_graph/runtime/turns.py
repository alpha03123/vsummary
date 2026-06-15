"""Agent 图的回合管理模块，负责构建图输入与解析图输出。

本模块定义：
- `GraphInputBundle`：绑定了 `AgentContext` 与图输入负载的数据类；
- `AgentGraphInputBuilder`：从会话上下文构建图初始状态；
- `AgentGraphTurnBuilder`：从图运行结果构建结构化的 `AgentTurnResult`。

"回合"（turn）指一次完整的"用户提问 → Agent 推理 → 回复"循环，是
`AgentGraphService` 的最小调度单元。
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentContextLoader, AgentSessionStore
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult, ScopeType
from backend.agent_graph.evidence.citations import build_citations_from_graph_result
from backend.agent_graph.runtime.outcome import extract_assistant_message, extract_reason, extract_tool_results
from backend.agent_graph.runtime.state import AgentGraphState


@dataclass(frozen=True)
class GraphInputBundle:
    """图的输入包，将 `AgentContext` 与图状态负载绑定在一起。

    `AgentGraphInputBuilder.build()` 返回此结构，上游可分别取用上下文
    与图输入字典，避免重复传递。

    Attributes:
        context: 当前会话的 `AgentContext`（scope、目标资源等）。
        payload: `AgentGraphState` 字典，作为图的初始状态。
    """
    context: AgentContext
    payload: AgentGraphState


class AgentGraphInputBuilder:
    """构建图输入包的建造者，负责从会话上下文组装 `AgentGraphState`。

    业务意图：每个回合开始时，需要将"当前 Agent 上下文 + 多轮对话历史 +
    用户新问题"打包为图的初始状态。本建造者从 `AgentContextLoader` 加载
    上下文，从 `AgentSessionStore` 读取历史消息，组装成 `GraphInputBundle`。

    关键不变式：
    - `context_override` 非空时优先使用，否则从 `context_loader` 加载；
    - `session_store` 为 `None` 时 memory_messages 为空列表。
    """

    def __init__(
        self,
        *,
        context_loader: AgentContextLoader,
        session_store: AgentSessionStore | None = None,
    ) -> None:
        """注入上下文加载器与会话存储端口。

        Args:
            context_loader: 从会话 ID 加载 `AgentContext` 的端口。
            session_store: 可选的会话持久化端口，用于读取历史消息；
                为 `None` 时 memory_messages 为空。
        """
        self._context_loader = context_loader
        self._session_store = session_store

    @property
    def context_loader(self) -> AgentContextLoader:
        """已注入的上下文加载器端口。"""
        return self._context_loader

    @property
    def session_store(self) -> AgentSessionStore | None:
        """已注入的会话存储端口；可能为 `None`."""
        return self._session_store

    def build(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override: AgentContext | None = None,
    ) -> GraphInputBundle:
        """从会话上下文构建图输入包。

        加载 `AgentContext`（优先使用覆盖值）、读取多轮历史消息，与用户
        新问题一起组装为 `AgentGraphState`。

        Args:
            session_id: 会话唯一 ID。
            user_message: 用户最新问题原文。
            context_override: 可选的 `AgentContext` 覆盖值；为 `None` 时从
                `context_loader` 自动加载。

        Returns:
            绑定了 `AgentContext` 与 `AgentGraphState` 的 `GraphInputBundle`。
        """
        context = context_override or self._context_loader.load(session_id)
        memory_messages: list[dict[str, object]] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                memory_messages = [
                    {"role": item.role, "content": item.content}
                    for item in snapshot.messages
                ]
        return GraphInputBundle(
            context=context,
            payload={
                "session_id": session_id,
                "scope_type": context.scope_type,
                "series_id": context.series_id or "",
                "video_id": context.video_id or "",
                "user_message": user_message,
                "memory_messages": memory_messages,
            },
        )


class AgentGraphTurnBuilder:
    """将图运行结果构建为结构化 `AgentTurnResult` 的建造者。

    业务意图：图的最终状态是一个松散字典，而下游（路由、会话记录）需要
    类型化的 `AgentTurnResult`。本建造者从图状态中提取助手消息、工具调用
    结果与引用信息，组装为统一的回合结果结构。

    关键不变式：
    - `assistant_message` 从 `result["answer"]` 或 `result["assistant_message"]` 提取；
    - `plan.reason` 从 `result["reason"]` 提取，缺失时为空字符串；
    - 引用由 `build_citations_from_graph_result` 从多来源（evidence_items、
      retrieval_results 等）统一构建。
    """

    def build(
        self,
        *,
        context: AgentContext,
        result: dict[str, object],
        debug_trace: dict[str, object] | None = None,
    ) -> AgentTurnResult:
        """从图运行结果构建 `AgentTurnResult`。

        提取助手消息、工具调用结果、推理原因与引用，组装为结构化回合结果。
        若提供了 debug_trace，同时将这些字段写入调试字典。

        Args:
            context: 当前会话的 `AgentContext`，用于推导 `ScopeType`。
            result: 图运行结束后的最终状态字典。
            debug_trace: 可选的调试信息收集字典；为 `None` 时不记录。

        Returns:
            含助手消息、计划、工具结果与引用的 `AgentTurnResult`。
        """
        assistant_message = extract_assistant_message(result)
        tool_results = extract_tool_results(result)
        citations = build_citations_from_graph_result(result)
        turn_result = AgentTurnResult(
            assistant_message=assistant_message,
            plan=AgentActionPlan(
                scope_type=ScopeType(context.scope_type),
                tool_calls=[],
                reason=extract_reason(result),
                use_answerer=bool(str(result.get("answer", "")).strip()),
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
