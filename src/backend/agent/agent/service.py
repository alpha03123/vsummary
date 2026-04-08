from __future__ import annotations

from collections.abc import Iterator

from backend.agent.context.compact import AgentMemoryCompactionService
from backend.agent.memory.context import AgentContext
from backend.agent.memory.runtime import load_runtime_context
from backend.agent.memory.store import AgentMemoryStore, InMemoryAgentMemoryStore
from backend.agent.ports import AgentContextLoader, AgentSessionStore, AgentToolExecutor, ChatGateway
from backend.agent.runtime.assistant_runtime import AssistantRuntime, RuntimeExecutionResult
from backend.agent.runtime.tool_loop import apply_tool_result_to_context as _apply_tool_result_to_context
from backend.agent.session.evidence_cache import restore_cached_tool_results
from backend.agent.schemas.action_plan import AgentTurnResult
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent.schemas.tool_calls import ToolExecutionResult


class AgentService:
    def __init__(
        self,
        gateway: ChatGateway,
        context_loader: AgentContextLoader,
        memory_store: AgentMemoryStore | None = None,
        session_store: AgentSessionStore | None = None,
        memory_compaction_service: AgentMemoryCompactionService | None = None,
        tool_executor: AgentToolExecutor | None = None,
        projection_max_tokens: int | None = None,
    ) -> None:
        self._gateway = gateway
        self._context_loader = context_loader
        self._memory_store = memory_store or InMemoryAgentMemoryStore()
        self._session_store = session_store
        self._memory_compaction_service = memory_compaction_service
        if tool_executor is None:
            raise RuntimeError("AgentService 需要显式提供 tool_executor。")
        self._tool_executor = tool_executor
        self._runtime = AssistantRuntime(
            gateway=gateway,
            tool_executor=self._tool_executor,
            projection_max_tokens=projection_max_tokens,
        )

    def run(self, session_id: str, user_message: str) -> AgentTurnResult:
        return self.run_with_context(session_id=session_id, user_message=user_message, context_override=None)

    def run_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override: AgentContext | None,
    ) -> AgentTurnResult:
        self._compact_memory_if_needed(session_id, context_override)
        context, memory_key = self._load_runtime_context(session_id, context_override)
        runtime_result = self._runtime.run(
            context=context,
            memory_key=memory_key,
            user_message=user_message,
            cached_tool_results=self._load_cached_tool_results(session_id),
        )
        self._persist_turn(
            session_id=session_id,
            memory_key=memory_key,
            runtime_result=runtime_result,
            user_message=user_message,
        )
        return AgentTurnResult(
            assistant_message=runtime_result.assistant_message,
            plan=runtime_result.plan,
            tool_results=runtime_result.tool_results,
        )

    def stream_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override: AgentContext | None,
    ) -> Iterator[AgentStreamEvent]:
        self._compact_memory_if_needed(session_id, context_override)
        context, memory_key = self._load_runtime_context(session_id, context_override)
        runtime_stream = self._runtime.stream(
            context=context,
            memory_key=memory_key,
            user_message=user_message,
            cached_tool_results=self._load_cached_tool_results(session_id),
        )
        while True:
            try:
                event = next(runtime_stream)
            except StopIteration as completed:
                runtime_result = completed.value
                break
            yield event
        self._persist_turn(
            session_id=session_id,
            memory_key=memory_key,
            runtime_result=runtime_result,
            user_message=user_message,
        )

    def clear_session(
        self,
        *,
        session_id: str,
        context_override: AgentContext | None,
    ) -> None:
        context, memory_key = self._load_runtime_context(session_id, context_override)
        del context
        self._memory_store.clear_messages(memory_key)
        if self._session_store is not None:
            self._session_store.clear_snapshot(session_id)

    def _load_runtime_context(
        self,
        session_id: str,
        context_override: AgentContext | None,
    ) -> tuple[AgentContext, str]:
        context, memory_key, _history = load_runtime_context(
            context_loader=self._context_loader,
            memory_store=self._memory_store,
            session_id=session_id,
            context_override=context_override,
            session_store=self._session_store,
        )
        return context, memory_key

    def _persist_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        runtime_result: RuntimeExecutionResult,
        user_message: str,
    ) -> None:
        self._memory_store.append_messages(
            memory_key,
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=runtime_result.assistant_message),
            ],
        )
        self._record_session_turn(
            session_id=session_id,
            memory_key=memory_key,
            context=runtime_result.context,
            user_message=user_message,
            assistant_message=runtime_result.assistant_message,
            tool_results=runtime_result.tool_results,
        )

    def _record_session_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        user_message: str,
        assistant_message: str,
        tool_results: list[ToolExecutionResult],
    ) -> None:
        if self._session_store is None:
            return
        self._session_store.append_turn(
            session_id=session_id,
            memory_key=memory_key,
            context=context,
            user_message=user_message,
            assistant_message=assistant_message,
            tool_results=tool_results,
        )

    def _compact_memory_if_needed(self, session_id: str, context_override: AgentContext | None) -> None:
        if self._memory_compaction_service is None:
            return
        context, memory_key = self._load_runtime_context(session_id, context_override)
        del context
        self._memory_compaction_service.compact_if_needed(memory_key)

    def _load_cached_tool_results(self, session_id: str) -> list[ToolExecutionResult]:
        if self._session_store is None:
            return []
        snapshot = self._session_store.get_snapshot(session_id)
        if snapshot is None:
            return []
        return restore_cached_tool_results(snapshot.evidence_entries)
