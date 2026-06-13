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
    def search(self, **kwargs):
        raise RuntimeError(
            "Series retrieval service 尚未注入。请在集成阶段传入 retrieval_service，"
            "或在后续任务里接入基于 workspace / LlamaIndex 的默认实现。"
        )


class _MissingAnswerProgram:
    def run(self, **kwargs):
        del kwargs
        raise RuntimeError("Video answer synthesis program 尚未注入。")


def _route_after_scope(state: AgentGraphState) -> str:
    if str(state.get("scope_type", "")).strip() == "series":
        return "series"
    if str(state.get("scope_type", "")).strip() == "video":
        return "video"
    raise ValueError(f"Unsupported scope_type: {state.get('scope_type', '')}")


def _route_after_evidence_items(state: AgentGraphState) -> str:
    return _route_after_scope(state)
