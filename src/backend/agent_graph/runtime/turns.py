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
    context: AgentContext
    payload: AgentGraphState


class AgentGraphInputBuilder:
    def __init__(
        self,
        *,
        context_loader: AgentContextLoader,
        session_store: AgentSessionStore | None = None,
    ) -> None:
        self._context_loader = context_loader
        self._session_store = session_store

    @property
    def context_loader(self) -> AgentContextLoader:
        return self._context_loader

    @property
    def session_store(self) -> AgentSessionStore | None:
        return self._session_store

    def build(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override: AgentContext | None = None,
    ) -> GraphInputBundle:
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
    def build(
        self,
        *,
        context: AgentContext,
        result: dict[str, object],
        debug_trace: dict[str, object] | None = None,
    ) -> AgentTurnResult:
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
