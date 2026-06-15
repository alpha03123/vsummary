"""Agent Graph 的 StateGraph 定义与按 scope 的条件路由。

本模块集中描述 LangGraph 的节点、边与条件路由：
- `build_agent_graph`：根据可选依赖构建并编译完整的图；
- `route_scope` 之后的条件分支由 `_route_after_scope` 决定走 series 还是
  video 链路；
- 在证据整理（`build_evidence_items`）后再次按 scope 分流：series 进入
  `synthesize_answer`，video 进入 `plan_and_execute_video_actions` → `answer`；
- 未注入的检索/视频回答组件会使用 `_MissingRetrievalService` /
  `_MissingAnswerProgram` 哨兵，运行到对应节点时报错提醒补依赖。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent_graph.runtime.nodes import (
    build_route_scope_node,
    build_answer_node,
    build_evidence_items_node,
    build_optional_web_search_node,
    build_retrieve_evidence_node,
    build_synthesize_answer_node,
    build_understand_query_node,
    build_plan_and_execute_video_actions_node,
    build_video_context_node,
    finalize_state,
)
from backend.agent_graph.query.video_answer_synthesizer import (
    AnswerSynthesisProgram,
)
from backend.agent_graph.runtime.state import AgentGraphState


def build_agent_graph(
    *,
    retrieval_service=None,
    answer_program=None,
    series_query_processor=None,
    series_answer_synthesizer=None,
    workspace=None,
    video_action_planner=None,
    tool_executor=None,
    context_window_tokens=1_000_000,
    reserved_output_tokens=20_000,
    web_search_gateway=None,
    web_search_settings=None,
):
    """根据可选依赖构建并编译完整的 Agent Graph。

    Args:
        retrieval_service: 系列级 RAG 检索服务（`SeriesRetrievalService` 或兼容实现），
            为 `None` 时使用 `_MissingRetrievalService` 哨兵，运行到检索时报错。
        answer_program: video scope 的回答合成程序（实现 `AnswerSynthesisProgram`），
            为 `None` 时使用 `_MissingAnswerProgram` 哨兵。
        series_query_processor: series scope 的查询理解处理器。
        series_answer_synthesizer: series scope 的回答合成器。
        workspace: 工作区只读端口（视频/系列/制品读取）。
        video_action_planner: video scope 的动作规划器。
        tool_executor: 视频工具执行器端口。
        context_window_tokens: video scope 上下文窗口上限（默认 1,000,000）。
        reserved_output_tokens: 预留输出 token（默认 20,000）。
        web_search_gateway: 联网搜索网关（`None` 时跳过联网节点）。
        web_search_settings: 联网搜索配置（`enabled=False` 时跳过）。

    Returns:
        编译好的 LangGraph 图对象，可直接 `invoke` / `stream`。
    """
    resolved_retrieval_service = retrieval_service or _MissingRetrievalService()
    resolved_answer_program = answer_program or _MissingAnswerProgram()

    graph = StateGraph(AgentGraphState)
    graph.add_node("route_scope", build_route_scope_node())
    graph.add_node(
        "build_video_context",
        build_video_context_node(
            workspace=workspace,
            retrieval_service=resolved_retrieval_service,
            context_window_tokens=context_window_tokens,
            reserved_output_tokens=reserved_output_tokens,
        ),
    )
    graph.add_node(
        "understand_query",
        build_understand_query_node(
            series_query_processor=series_query_processor,
            workspace=workspace,
        ),
    )
    graph.add_node(
        "retrieve_evidence",
        build_retrieve_evidence_node(retrieval_service=resolved_retrieval_service),
    )
    graph.add_node(
        "optional_web_search",
        build_optional_web_search_node(
            web_search_gateway=web_search_gateway,
            web_search_settings=web_search_settings,
        ),
    )
    graph.add_node("build_evidence_items", build_evidence_items_node())
    graph.add_node(
        "synthesize_answer",
        build_synthesize_answer_node(series_answer_synthesizer=series_answer_synthesizer),
    )
    graph.add_node(
        "answer",
        build_answer_node(answer_program=resolved_answer_program),
    )
    graph.add_node(
        "plan_and_execute_video_actions",
        build_plan_and_execute_video_actions_node(
            video_action_planner=video_action_planner,
            tool_executor=tool_executor,
        ),
    )
    graph.add_node("finalize", finalize_state)
    graph.add_edge(START, "route_scope")
    graph.add_conditional_edges(
        "route_scope",
        _route_after_scope,
        {
            "series": "understand_query",
            "video": "build_video_context",
        },
    )
    graph.add_edge("understand_query", "retrieve_evidence")
    graph.add_edge("retrieve_evidence", "optional_web_search")
    graph.add_edge("optional_web_search", "build_evidence_items")
    graph.add_edge("synthesize_answer", "finalize")
    graph.add_edge("build_video_context", "optional_web_search")
    graph.add_conditional_edges(
        "build_evidence_items",
        _route_after_evidence_items,
        {
            "series": "synthesize_answer",
            "video": "plan_and_execute_video_actions",
        },
    )
    graph.add_edge("plan_and_execute_video_actions", "answer")
    graph.add_edge("answer", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


class _MissingRetrievalService:
    """检索服务未注入时的哨兵：调用 `search` 时直接抛错。"""

    def search(self, **kwargs):
        """触发未注入错误，提醒接入真正的 RAG 检索实现。"""
        raise RuntimeError(
            "Series retrieval service 尚未注入。请在集成阶段传入 retrieval_service，"
            "或在后续任务里接入基于 workspace / LlamaIndex 的默认实现。"
        )


class _MissingAnswerProgram:
    """video scope 回答程序未注入时的哨兵：调用 `run` 时直接抛错。"""

    def run(self, **kwargs):
        """触发未注入错误，提醒接入 `AnswerSynthesisProgram`。"""
        del kwargs
        raise RuntimeError("Video answer synthesis program 尚未注入。")


def _route_after_scope(state: AgentGraphState) -> str:
    """按 `scope_type` 决定走 series 还是 video 链路。

    Args:
        state: 当前 `AgentGraphState`。

    Returns:
        `"series"` 或 `"video"` 字符串，作为条件边的分支键。

    Raises:
        ValueError: `scope_type` 既不是 `"series"` 也不是 `"video"`。
    """
    if str(state.get("scope_type", "")).strip() == "series":
        return "series"
    if str(state.get("scope_type", "")).strip() == "video":
        return "video"
    raise ValueError(f"Unsupported scope_type: {state.get('scope_type', '')}")


def _route_after_evidence_items(state: AgentGraphState) -> str:
    """在 `build_evidence_items` 之后再次按 scope 路由（series 合成 / video 规划执行）。"""
    return _route_after_scope(state)
