from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent_graph.runtime.nodes import (
    build_advance_task_node,
    build_advance_subplan_node,
    build_answer_node,
    build_plan_node,
    build_decompose_node,
    build_dispatch_action_node,
    build_execute_series_meta_node,
    build_execute_summary_node,
    build_execute_video_rag_node,
    build_execute_video_graph_node,
    build_execute_video_workflow_node,
    build_finalize_node,
    build_read_meta_state_node,
    build_update_memory_node,
)
from backend.agent_graph.query.models import ExecutionDepth
from backend.agent_graph.dspy.programs import (
    AnswerSynthesisProgram,
    CompareSplitProgram,
    MemoryUpdateProgram,
    SeriesQueryClassifierProgram,
    TaskDecomposerProgram,
)
from backend.agent_graph.runtime.state import AgentGraphState


def build_agent_graph(
    *,
    decomposer_program=None,
    classifier_program=None,
    compare_split_program=None,
    series_planner=None,
    retrieval_service=None,
    pinpoint_service=None,
    workflow_service=None,
    meta_state_reader=None,
    action_dispatcher=None,
    answer_program=None,
    series_aggregator=None,
    memory_update_program=None,
):
    resolved_decomposer_program = decomposer_program or TaskDecomposerProgram()
    resolved_classifier_program = classifier_program or SeriesQueryClassifierProgram()
    resolved_compare_split_program = compare_split_program or CompareSplitProgram()
    resolved_retrieval_service = retrieval_service or _MissingRetrievalService()
    resolved_pinpoint_service = pinpoint_service or _MissingPinpointService()
    resolved_workflow_service = workflow_service or _MissingWorkflowService()
    resolved_meta_state_reader = meta_state_reader or _MissingMetaStateReader()
    resolved_action_dispatcher = action_dispatcher or _MissingActionDispatcher()
    resolved_answer_program = answer_program or AnswerSynthesisProgram()
    resolved_memory_update_program = memory_update_program or MemoryUpdateProgram()

    graph = StateGraph(AgentGraphState)
    graph.add_node("decompose", build_decompose_node(decomposer_program=resolved_decomposer_program))
    graph.add_node("advance_task", build_advance_task_node())
    graph.add_node(
        "build_plan",
        build_plan_node(
            classifier_program=resolved_classifier_program,
            compare_split_program=resolved_compare_split_program,
            series_planner=series_planner,
        ),
    )
    graph.add_node("advance_subplan", build_advance_subplan_node())
    graph.add_node("execute_series_meta", build_execute_series_meta_node(meta_state_reader=resolved_meta_state_reader))
    graph.add_node("execute_summary", build_execute_summary_node(retrieval_service=resolved_retrieval_service))
    graph.add_node(
        "execute_video_graph",
        build_execute_video_graph_node(
            retrieval_service=resolved_retrieval_service,
            pinpoint_service=resolved_pinpoint_service,
        ),
    )
    graph.add_node(
        "execute_video_rag",
        build_execute_video_rag_node(retrieval_service=resolved_retrieval_service),
    )
    graph.add_node(
        "execute_video_workflow",
        build_execute_video_workflow_node(workflow_service=resolved_workflow_service),
    )
    graph.add_node("read_meta_state", build_read_meta_state_node(meta_state_reader=resolved_meta_state_reader))
    graph.add_node("dispatch_action", build_dispatch_action_node(action_dispatcher=resolved_action_dispatcher))
    graph.add_node("answer", build_answer_node(answer_program=resolved_answer_program, series_aggregator=series_aggregator))
    graph.add_node("finalize", build_finalize_node())
    graph.add_node("update_memory", build_update_memory_node(memory_update_program=resolved_memory_update_program))
    graph.add_edge(START, "decompose")
    graph.add_edge("decompose", "advance_task")
    graph.add_edge("advance_task", "build_plan")
    graph.add_conditional_edges(
        "build_plan",
        _route_after_build_plan,
        {
            "dispatch_action": "dispatch_action",
            "read_meta_state": "read_meta_state",
            "advance_subplan": "advance_subplan",
            "answer": "answer",
        },
    )
    graph.add_conditional_edges(
        "advance_subplan",
        _route_after_advance_subplan,
        {
            "execute_series_meta": "execute_series_meta",
            "execute_summary": "execute_summary",
            "execute_video_graph": "execute_video_graph",
            "execute_video_rag": "execute_video_rag",
            "execute_video_workflow": "execute_video_workflow",
            "answer": "answer",
        },
    )
    graph.add_conditional_edges(
        "execute_series_meta",
        _route_after_subplan_execution,
        {
            "advance_subplan": "advance_subplan",
            "answer": "answer",
        },
    )
    graph.add_conditional_edges(
        "execute_summary",
        _route_after_subplan_execution,
        {
            "advance_subplan": "advance_subplan",
            "answer": "answer",
        },
    )
    graph.add_conditional_edges(
        "execute_video_graph",
        _route_after_subplan_execution,
        {
            "advance_subplan": "advance_subplan",
            "answer": "answer",
        },
    )
    graph.add_conditional_edges(
        "execute_video_rag",
        _route_after_subplan_execution,
        {
            "advance_subplan": "advance_subplan",
            "answer": "answer",
        },
    )
    graph.add_conditional_edges(
        "execute_video_workflow",
        _route_after_subplan_execution,
        {
            "advance_subplan": "advance_subplan",
            "answer": "answer",
        },
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
    graph.add_edge("finalize", "update_memory")
    graph.add_edge("update_memory", END)
    return graph.compile()


def build_series_agent_graph(
    *,
    decomposer_program=None,
    classifier_program=None,
    compare_split_program=None,
    series_planner=None,
    retrieval_service=None,
    pinpoint_service=None,
    workflow_service=None,
    meta_state_reader=None,
    action_dispatcher=None,
    answer_program=None,
    series_aggregator=None,
    memory_update_program=None,
):
    return build_agent_graph(
        decomposer_program=decomposer_program,
        classifier_program=classifier_program,
        compare_split_program=compare_split_program,
        series_planner=series_planner,
        retrieval_service=retrieval_service,
        pinpoint_service=pinpoint_service,
        workflow_service=workflow_service,
        meta_state_reader=meta_state_reader,
        action_dispatcher=action_dispatcher,
        answer_program=answer_program,
        series_aggregator=series_aggregator,
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


class _MissingPinpointService:
    def locate(self, **kwargs):
        raise RuntimeError(
            "Pinpoint service 尚未注入。请在集成阶段传入 pinpoint_service，"
            "或在后续任务里接入基于 transcript 的默认实现。"
        )


class _MissingWorkflowService:
    def extract(self, **kwargs):
        raise RuntimeError(
            "Workflow service 尚未注入。请在集成阶段传入 workflow_service，"
            "或在后续任务里接入基于 transcript 的连续流程抽取实现。"
        )


def _route_after_build_plan(state: AgentGraphState) -> str:
    goal = str(state.get("query_plan", {}).get("goal", "")).strip()
    if goal == "action":
        return "dispatch_action"
    if goal == "meta_state":
        return "read_meta_state"
    subplans = list(state.get("query_plan", {}).get("subplans", []))
    if subplans:
        return "advance_subplan"
    return "answer"


def _route_after_advance_subplan(state: AgentGraphState) -> str:
    current_subplan = dict(state.get("current_subplan", {}))
    depth = str(current_subplan.get("depth", "")).strip()
    if depth == ExecutionDepth.SERIES_META.value:
        return "execute_series_meta"
    if depth == ExecutionDepth.SUMMARY.value:
        return "execute_summary"
    if depth == ExecutionDepth.VIDEO_GRAPH.value:
        return "execute_video_graph"
    if depth == ExecutionDepth.VIDEO_RAG.value:
        return "execute_video_rag"
    if depth == ExecutionDepth.VIDEO_WORKFLOW.value:
        return "execute_video_workflow"
    return "answer"


def _route_after_subplan_execution(state: AgentGraphState) -> str:
    subplans = list(state.get("query_plan", {}).get("subplans", []))
    current_index = int(state.get("current_subplan_index", -1))
    if current_index + 1 < len(subplans):
        return "advance_subplan"
    return "answer"


def _route_after_completed_task(state: AgentGraphState) -> str:
    tasks = list(state.get("tasks", []))
    index = int(state.get("current_task_index", 0))
    if index + 1 < len(tasks):
        return "advance_task"
    return "finalize"
