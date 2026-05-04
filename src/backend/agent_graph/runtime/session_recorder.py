from __future__ import annotations

from backend.agent.memory.context import AgentContext
from backend.agent.memory.dialog_history import DialogHistoryCompactor, render_dialog_history
from backend.agent.ports import AgentSessionStore
from backend.agent.schemas.action_plan import AgentTurnResult
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent_graph.runtime.outcome import (
    extract_history_summary_update,
    merge_evidence_history,
)


class AgentGraphSessionRecorder:
    def __init__(
        self,
        *,
        session_store: AgentSessionStore | None = None,
        dialog_history_compactor: DialogHistoryCompactor | None = None,
    ) -> None:
        self._session_store = session_store
        self._dialog_history_compactor = dialog_history_compactor

    @property
    def session_store(self) -> AgentSessionStore | None:
        return self._session_store

    def persist_turn(
        self,
        *,
        session_id: str,
        context: AgentContext,
        user_message: str,
        result: dict[str, object],
        turn_result: AgentTurnResult,
    ) -> None:
        if self._session_store is None:
            return
        dialog_history = self._build_next_dialog_history(
            session_id=session_id,
            user_message=user_message,
            assistant_message=turn_result.assistant_message,
        )
        persisted_context = context.model_copy(
            update={
                "dialog_history": dialog_history,
                "evidence_history": merge_evidence_history(
                    current=dict(getattr(context, "evidence_history", {}) or {}),
                    result=result,
                ),
                "history_summary": extract_history_summary_update(
                    result,
                    fallback=str(getattr(context, "history_summary", "") or ""),
                ),
            }
        )
        self._session_store.append_turn(
            session_id=session_id,
            memory_key=session_id,
            context=persisted_context,
            user_message=user_message,
            assistant_message=turn_result.assistant_message,
            tool_results=turn_result.tool_results,
            selected_videos=[],
        )

    def clear_session(self, session_id: str) -> None:
        if self._session_store is not None:
            self._session_store.clear_snapshot(session_id)

    def _build_next_dialog_history(
        self,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
    ) -> str:
        messages: list[AgentChatMessage] = []
        if self._session_store is not None:
            snapshot = self._session_store.get_snapshot(session_id)
            if snapshot is not None:
                messages.extend(
                    AgentChatMessage(role=item.role, content=item.content)
                    for item in snapshot.messages
                )
        messages.extend(
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=assistant_message),
            ]
        )
        if self._dialog_history_compactor is not None:
            return self._dialog_history_compactor.compact_if_needed(messages)
        return render_dialog_history(messages)
