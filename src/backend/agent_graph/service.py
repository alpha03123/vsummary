from __future__ import annotations

from collections.abc import Iterator

from backend.agent.ports import AgentContextLoader
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult, ScopeType
from backend.agent_graph.citations import build_citations_from_graph_result
from backend.agent.session.models import AgentSessionSelectedVideoEntry
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


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
        memory_update_program=None,
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
        self._memory_update_program = memory_update_program

    @property
    def graph(self):
        return self._graph

    def _invoke_graph(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
        debug_trace: dict[str, object] | None = None,
    ) -> dict[str, object]:
        context = context_override or self._context_loader.load(session_id)
        history_messages: list[dict[str, object]] = []
        history_summary = ""
        history_selected_videos: list[dict[str, object]] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                history_messages = [
                    {"role": item.role, "content": item.content}
                    for item in snapshot.messages
                ]
                history_summary = snapshot.context.compact_summary
                history_selected_videos = [
                    {
                        "video_id": item.video_id,
                        "reason_for_selection": item.reason_for_selection,
                    }
                    for item in snapshot.selected_videos
                ]
        result = self._graph.invoke(
            {
                "session_id": session_id,
                "scope_type": context.scope_type,
                "series_id": context.series_id or "",
                "video_id": context.video_id or "",
                "user_message": user_message,
                "history_messages": history_messages,
                "history_summary": history_summary,
                "history_selected_videos": history_selected_videos,
            }
        )
        if debug_trace is not None:
            debug_trace["graph_input"] = {
                "session_id": session_id,
                "scope_type": context.scope_type,
                "series_id": context.series_id or "",
                "video_id": context.video_id or "",
                "history_message_count": len(history_messages),
                "history_summary": history_summary,
                "history_selected_videos": history_selected_videos,
                "user_message": user_message,
            }
            debug_trace["graph_result"] = result
        return result

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
        context = context_override or self._context_loader.load(session_id)
        result = self._invoke_graph(
            session_id=session_id,
            user_message=user_message,
            context_override=context,
            debug_trace=debug_trace,
        )
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
        if self._session_store is not None:
            compact_summary = str(result.get("history_summary_update", "")).strip()
            persisted_context = context.model_copy(
                update={
                    "compact_summary": compact_summary or context.compact_summary,
                }
            )
            self._session_store.append_turn(
                session_id=session_id,
                memory_key=session_id,
                context=persisted_context,
                user_message=user_message,
                assistant_message=assistant_message,
                tool_results=tool_results,
                selected_videos=[
                    AgentSessionSelectedVideoEntry(
                        video_id=str(item.get("video_id", "")).strip(),
                        reason_for_selection=str(item.get("reason_for_selection", "")).strip(),
                    )
                    for item in _extract_selected_videos(result)
                    if str(item.get("video_id", "")).strip()
                ],
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
        yield AgentStreamEvent(type="thinking_started", payload={"message": "正在分析当前问题"})
        turn_result = self.run_turn(
            session_id=session_id,
            user_message=user_message,
            context_override=context_override,
            debug_trace=debug_trace,
        )
        yield AgentStreamEvent(type="thinking_completed", payload={"summary": "graph 已生成结构化决策"})
        for tool_result in turn_result.tool_results:
            yield AgentStreamEvent(
                type="tool_completed",
                payload={
                    "tool_name": tool_result.tool_name.value,
                    "status": tool_result.status,
                    "payload": tool_result.payload,
                },
            )
        yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
        yield AgentStreamEvent(
            type="answer_completed",
            payload={"message": turn_result.assistant_message},
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
