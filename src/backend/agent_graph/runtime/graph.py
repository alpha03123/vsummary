from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from backend.agent.tools.context_access import render_model_visible_actions_for_scope
from backend.agent_graph.runtime.nodes import (
    build_route_scope_node,
    build_advance_subplan_node,
    build_answer_node,
    build_dispatch_action_node,
    build_retrieve_evidence_node,
    build_execute_series_meta_node,
    build_execute_summary_node,
    build_synthesize_answer_node,
    build_understand_query_node,
    build_execute_video_graph_node,
    build_execute_video_rag_node,
    build_execute_video_workflow_node,
    build_plan_node,
    build_read_meta_state_node,
    apply_memory_update,
    finalize_state,
)
from backend.agent_graph.query.models import ExecutionDepth
from backend.agent_graph.dspy.programs import (
    ActionAfterContentReplyProgram,
    AnswerSynthesisProgram,
    CompareSplitProgram,
    NoteSynthesisProgram,
    SeriesQueryClassifierProgram,
)
from backend.agent_graph.runtime.state import AgentGraphState


def build_agent_graph(
    *,
    classifier_program=None,
    compare_split_program=None,
    retrieval_service=None,
    pinpoint_service=None,
    workflow_service=None,
    meta_state_reader=None,
    action_dispatcher=None,
    answer_program=None,
    note_program=None,
    action_reply_program=None,
    series_query_processor=None,
    series_answer_synthesizer=None,
    workspace=None,
):
    resolved_classifier_program = classifier_program or SeriesQueryClassifierProgram(
        available_actions_resolver=render_model_visible_actions_for_scope,
    )
    resolved_compare_split_program = compare_split_program or CompareSplitProgram()
    resolved_retrieval_service = retrieval_service or _MissingRetrievalService()
    resolved_pinpoint_service = pinpoint_service or _MissingPinpointService()
    resolved_workflow_service = workflow_service or _MissingWorkflowService()
    resolved_meta_state_reader = meta_state_reader or _MissingMetaStateReader()
    resolved_action_dispatcher = action_dispatcher or _MissingActionDispatcher()
    resolved_answer_program = answer_program or AnswerSynthesisProgram()
    resolved_note_program = note_program or NoteSynthesisProgram()
    resolved_action_reply_program = action_reply_program or ActionAfterContentReplyProgram()

    graph = StateGraph(AgentGraphState)
    graph.add_node("route_scope", build_route_scope_node())
    graph.add_node(
        "build_plan",
        build_plan_node(
            classifier_program=resolved_classifier_program,
            compare_split_program=resolved_compare_split_program,
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
        "synthesize_answer",
        build_synthesize_answer_node(series_answer_synthesizer=series_answer_synthesizer),
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
    graph.add_node(
        "answer",
        build_answer_node(
            answer_program=resolved_answer_program,
            note_program=resolved_note_program,
            action_reply_program=resolved_action_reply_program,
        ),
    )
    graph.add_node("finalize", finalize_state)
    graph.add_node("update_session_memory", apply_memory_update)
    graph.add_edge(START, "route_scope")
    graph.add_conditional_edges(
        "route_scope",
        _route_after_scope,
        {
            "series": "understand_query",
            "default": "build_plan",
        },
    )
    graph.add_conditional_edges(
        "build_plan",
        _route_after_build_plan,
        {
            "dispatch_action": "dispatch_action",
            "read_meta_state": "read_meta_state",
            "advance_subplan": "advance_subplan",
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
    graph.add_edge("understand_query", "retrieve_evidence")
    graph.add_edge("retrieve_evidence", "synthesize_answer")
    graph.add_edge("synthesize_answer", "finalize")
    graph.add_edge("read_meta_state", "answer")
    graph.add_edge("dispatch_action", "finalize")
    graph.add_conditional_edges(
        "answer",
        _route_after_answer,
        {
            "dispatch_action": "dispatch_action",
            "finalize": "finalize",
        },
    )
    graph.add_edge("finalize", "update_session_memory")
    graph.add_edge("update_session_memory", END)
    return graph.compile()


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
    return "advance_subplan"


def _route_after_scope(state: AgentGraphState) -> str:
    if str(state.get("scope_type", "")).strip() == "series":
        return "series"
    return "default"


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


def _route_after_answer(state: AgentGraphState) -> str:
    goal = str(state.get("query_plan", {}).get("goal", "")).strip()
    if goal == "action_after_content":
        return "dispatch_action"
    return "finalize"
