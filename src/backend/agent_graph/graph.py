from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent_graph.nodes import (
    build_advance_task_node,
    build_answer_node,
    build_classify_node,
    build_decompose_node,
    build_dispatch_action_node,
    build_finalize_node,
    build_read_meta_state_node,
    build_retrieve_node,
    build_split_compare_node,
    build_update_memory_node,
)
from backend.agent_graph.programs import (
    AnswerSynthesisProgram,
    CompareSplitProgram,
    MemoryUpdateProgram,
    SeriesQueryClassifierProgram,
    TaskDecomposerProgram,
)
from backend.agent_graph.state import AgentGraphState


def build_agent_graph(
    *,
    decomposer_program=None,
    classifier_program=None,
    compare_split_program=None,
    retrieval_service=None,
    meta_state_reader=None,
    action_dispatcher=None,
    answer_program=None,
    memory_update_program=None,
):
    resolved_decomposer_program = decomposer_program or TaskDecomposerProgram()
    resolved_classifier_program = classifier_program or SeriesQueryClassifierProgram()
    resolved_compare_split_program = compare_split_program or CompareSplitProgram()
    resolved_retrieval_service = retrieval_service or _MissingRetrievalService()
    resolved_meta_state_reader = meta_state_reader or _MissingMetaStateReader()
    resolved_action_dispatcher = action_dispatcher or _MissingActionDispatcher()
    resolved_answer_program = answer_program or AnswerSynthesisProgram()
    resolved_memory_update_program = memory_update_program or MemoryUpdateProgram()

    graph = StateGraph(AgentGraphState)
    graph.add_node("decompose", build_decompose_node(decomposer_program=resolved_decomposer_program))
    graph.add_node("advance_task", build_advance_task_node())
    graph.add_node("classify", build_classify_node(classifier_program=resolved_classifier_program))
    graph.add_node("split_compare", build_split_compare_node(compare_split_program=resolved_compare_split_program))
    graph.add_node("retrieve", build_retrieve_node(retrieval_service=resolved_retrieval_service))
    graph.add_node("read_meta_state", build_read_meta_state_node(meta_state_reader=resolved_meta_state_reader))
    graph.add_node("dispatch_action", build_dispatch_action_node(action_dispatcher=resolved_action_dispatcher))
    graph.add_node("answer", build_answer_node(answer_program=resolved_answer_program))
    graph.add_node("finalize", build_finalize_node())
    graph.add_node("update_memory", build_update_memory_node(memory_update_program=resolved_memory_update_program))
    graph.add_edge(START, "decompose")
    graph.add_edge("decompose", "classify")
    graph.add_conditional_edges(
        "classify",
        _route_after_classify,
        {
            "dispatch_action": "dispatch_action",
            "read_meta_state": "read_meta_state",
            "split_compare": "split_compare",
            "retrieve": "retrieve",
        },
    )
    graph.add_conditional_edges(
        "split_compare",
        _route_after_split_compare,
        {
            "retrieve": "retrieve",
            "answer": "answer",
        },
    )
    graph.add_conditional_edges(
        "retrieve",
        lambda state: "answer",
        {"answer": "answer"},
    )
    graph.add_conditional_edges(
        "read_meta_state",
        lambda state: "answer",
        {"answer": "answer"},
    )
    graph.add_conditional_edges(
        "dispatch_action",
        _route_after_completed_task,
        {
            "advance_task": "advance_task",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "answer",
        _route_after_completed_task,
        {
            "advance_task": "advance_task",
            "finalize": "finalize",
        },
    )
    graph.add_edge("advance_task", "classify")
    graph.add_edge("finalize", "update_memory")
    graph.add_edge("update_memory", END)
    return graph.compile()


def build_series_agent_graph(
    *,
    decomposer_program=None,
    classifier_program=None,
    compare_split_program=None,
    retrieval_service=None,
    meta_state_reader=None,
    action_dispatcher=None,
    answer_program=None,
    memory_update_program=None,
):
    return build_agent_graph(
        decomposer_program=decomposer_program,
        classifier_program=classifier_program,
        compare_split_program=compare_split_program,
        retrieval_service=retrieval_service,
        meta_state_reader=meta_state_reader,
        action_dispatcher=action_dispatcher,
        answer_program=answer_program,
        memory_update_program=memory_update_program,
    )


class _MissingRetrievalService:
    def search(self, **kwargs):
        raise RuntimeError(
            "Series retrieval service 尚未注入。请在集成阶段传入 retrieval_service，"
            "或在后续任务里接入基于 workspace / LlamaIndex 的默认实现。"
        )


class _MissingMetaStateReader:
    def read(self, **kwargs):
        raise RuntimeError(
            "Meta state reader 尚未注入。请在集成阶段传入 meta_state_reader，"
            "或在后续任务里接入基于 workspace 的默认实现。"
        )


class _MissingActionDispatcher:
    def dispatch(self, **kwargs):
        raise RuntimeError(
            "Action dispatcher 尚未注入。请在集成阶段传入 action_dispatcher，"
            "或在后续任务里接入基于 tool executor 的默认实现。"
        )


def _route_after_classify(state: AgentGraphState) -> str:
    goal = str(state.get("query_plan", {}).get("goal", "")).strip()
    if goal == "action":
        return "dispatch_action"
    if goal == "meta_state":
        return "read_meta_state"
    if goal == "compare":
        return "split_compare"
    return "retrieve"


def _route_after_split_compare(state: AgentGraphState) -> str:
    queries = list(state.get("retrieval_queries", []))
    if queries:
        return "retrieve"
    return "answer"


def _route_after_completed_task(state: AgentGraphState) -> str:
    tasks = list(state.get("tasks", []))
    index = int(state.get("current_task_index", 0))
    if index + 1 < len(tasks):
        return "advance_task"
    return "finalize"
