from __future__ import annotations

from collections.abc import Iterator

from backend.agent.ports import AgentContextLoader
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult, ScopeType
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName


class AgentGraphService:
    def __init__(self, *, context_loader: AgentContextLoader, graph, session_store=None) -> None:
        self._context_loader = context_loader
        self._graph = graph
        self._session_store = session_store

    @property
    def graph(self):
        return self._graph

    def _invoke_graph(self, *, session_id: str, user_message: str) -> dict[str, object]:
        context = self._context_loader.load(session_id)
        history_messages: list[dict[str, object]] = []
        history_summary = ""
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                history_messages = [
                    {"role": item.role, "content": item.content}
                    for item in snapshot.messages
                ]
                history_summary = snapshot.context.compact_summary
        return self._graph.invoke(
            {
                "session_id": session_id,
                "scope_type": context.scope_type,
                "series_id": context.series_id or "",
                "video_id": context.video_id or "",
                "user_message": user_message,
                "history_messages": history_messages,
                "history_summary": history_summary,
            }
        )

    def run_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
    ) -> AgentTurnResult:
        del context_override
        return self.run_turn(session_id=session_id, user_message=user_message)

    def run(self, session_id: str, user_message: str) -> AgentTurnResult:  # type: ignore[override]
        return self.run_turn(session_id=session_id, user_message=user_message)

    def run_turn(self, *, session_id: str, user_message: str) -> AgentTurnResult:
        context = self._context_loader.load(session_id)
        result = self._invoke_graph(session_id=session_id, user_message=user_message)
        assistant_message = str(result.get("direct_response") or result.get("answer", "")).strip()
        tool_results = _build_tool_results(result)
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
        )
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
            )
        return turn_result

    def stream_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override=None,
    ) -> Iterator[AgentStreamEvent]:
        del context_override
        yield AgentStreamEvent(type="thinking_started", payload={"message": "正在分析当前问题"})
        turn_result = self.run_turn(session_id=session_id, user_message=user_message)
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
        del context_override
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
