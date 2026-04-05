from __future__ import annotations

from collections.abc import Iterator
from time import perf_counter
from typing import Callable

from backend.agent.agent.planner import extract_action_plan
from backend.agent.agent.responder import generate_assistant_message, stream_assistant_message
from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore, InMemoryAgentMemoryStore
from backend.agent.ports import AgentContextLoader, AgentToolExecutor, ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent.schemas.tool_calls import ToolExecutionResult
from backend.agent.validation.errors import AgentPlanError


class AgentService:
    def __init__(
        self,
        gateway: ChatGateway,
        context_loader: AgentContextLoader,
        memory_store: AgentMemoryStore | None = None,
        tool_executor: AgentToolExecutor | None = None,
    ) -> None:
        self._gateway = gateway
        self._context_loader = context_loader
        self._memory_store = memory_store or InMemoryAgentMemoryStore()
        self._tool_executor = tool_executor or RegistryAgentToolExecutor(registry={})

    def run(self, session_id: str, user_message: str) -> AgentTurnResult:
        return self.run_with_context(session_id=session_id, user_message=user_message, context_override=None)

    def run_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override: AgentContext | None,
    ) -> AgentTurnResult:
        context, memory_key = self._load_runtime_context(session_id, context_override)
        plan, tool_results = self._run_planning_loop(
            context=context,
            memory_key=memory_key,
            user_message=user_message,
        )
        assistant_message = generate_assistant_message(
            gateway=self._gateway,
            context=context,
            memory_store=self._memory_store,
            session_id=memory_key,
            user_message=user_message,
            plan=plan,
            tool_results=tool_results,
        )
        self._memory_store.append_messages(
            memory_key,
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=assistant_message),
            ],
        )
        return AgentTurnResult(
            assistant_message=assistant_message,
            plan=plan,
            tool_results=tool_results,
        )

    def stream_with_context(
        self,
        *,
        session_id: str,
        user_message: str,
        context_override: AgentContext | None,
    ) -> Iterator[AgentStreamEvent]:
        context, memory_key = self._load_runtime_context(session_id, context_override)
        plan, tool_results = yield from self._stream_planning_loop(
            context=context,
            memory_key=memory_key,
            user_message=user_message,
        )

        answer_started_at = perf_counter()
        yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
        chunks: list[str] = []
        for delta in stream_assistant_message(
            gateway=self._gateway,
            context=context,
            memory_store=self._memory_store,
            session_id=memory_key,
            user_message=user_message,
            plan=plan,
            tool_results=tool_results,
        ):
            chunks.append(delta)
            yield AgentStreamEvent(type="answer_delta", payload={"delta": delta})
        assistant_message = "".join(chunks).strip()
        if not assistant_message:
            raise RuntimeError("Agent 返回缺少 message.content。")
        yield AgentStreamEvent(
            type="answer_completed",
            payload={
                "message": assistant_message,
                "duration_ms": _elapsed_ms(answer_started_at),
            },
        )
        self._memory_store.append_messages(
            memory_key,
            [
                AgentChatMessage(role="user", content=user_message),
                AgentChatMessage(role="assistant", content=assistant_message),
            ],
        )

    def _stream_planning_loop(
        self,
        *,
        context: AgentContext,
        memory_key: str,
        user_message: str,
    ) -> Iterator[AgentStreamEvent]:
        observed_tool_results: list[ToolExecutionResult] = []
        final_plan: AgentActionPlan | None = None
        last_tool_plan: AgentActionPlan | None = None
        seen_calls: set[str] = set()
        overall_tool_started_at: float | None = None
        tool_event_index = 0

        for _round in range(4):
            thinking_started_at = perf_counter()
            yield AgentStreamEvent(type="thinking_started", payload={"message": "正在分析当前问题"})
            plan = self._extract_valid_action_plan(
                context=context,
                memory_key=memory_key,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
            )
            final_plan = plan
            reasoning_summary = _describe_plan_reason(plan.reason, plan)
            for chunk in _chunk_text(reasoning_summary):
                yield AgentStreamEvent(type="thinking_delta", payload={"delta": chunk})
            yield AgentStreamEvent(
                type="thinking_completed",
                payload={
                    "summary": reasoning_summary,
                    "duration_ms": _elapsed_ms(thinking_started_at),
                },
            )

            if not plan.tool_calls:
                if observed_tool_results and last_tool_plan is not None:
                    final_plan = last_tool_plan
                break

            if overall_tool_started_at is None:
                overall_tool_started_at = perf_counter()
            last_tool_plan = plan

            for call in plan.tool_calls:
                call_signature = call.model_dump_json(exclude_none=True)
                if call_signature in seen_calls:
                    raise RuntimeError("Agent 规划重复调用了相同工具，已中止本轮工具链。")
                seen_calls.add(call_signature)

                tool_event_index += 1
                tool_call_id = f"tool-{tool_event_index}"
                tool_started_at = perf_counter()
                yield AgentStreamEvent(
                    type="tool_started",
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": call.tool_name.value,
                        "index": tool_event_index,
                    },
                )
                result = self._tool_executor.execute_call(call, context)
                observed_tool_results.append(result)
                yield AgentStreamEvent(
                    type="tool_completed",
                    payload={
                        "tool_call_id": tool_call_id,
                        "tool_name": result.tool_name.value,
                        "status": result.status,
                        "payload": result.payload,
                        "duration_ms": _elapsed_ms(tool_started_at),
                    },
                )
        else:
            raise RuntimeError("Agent 工具链规划超过最大轮数，已中止本轮对话。")

        if final_plan is None:
            raise RuntimeError("Agent 未能生成有效规划。")

        if overall_tool_started_at is not None:
            yield AgentStreamEvent(
                type="tool_chain_completed",
                payload={
                    "count": len(observed_tool_results),
                    "duration_ms": _elapsed_ms(overall_tool_started_at),
                },
            )

        return final_plan, observed_tool_results

    def _load_runtime_context(
        self,
        session_id: str,
        context_override: AgentContext | None,
    ) -> tuple[AgentContext, str]:
        base_context = self._context_loader.load(session_id)
        context = _merge_context(base_context, context_override)
        memory_key = _build_memory_key(context, session_id)
        return _attach_recent_messages(context, self._memory_store.get_messages(memory_key)), memory_key

    def _run_planning_loop(
        self,
        *,
        context: AgentContext,
        memory_key: str,
        user_message: str,
        emit: Callable[[AgentStreamEvent], None] | None = None,
    ) -> tuple[AgentActionPlan, list[ToolExecutionResult]]:
        observed_tool_results: list[ToolExecutionResult] = []
        final_plan: AgentActionPlan | None = None
        last_tool_plan: AgentActionPlan | None = None
        seen_calls: set[str] = set()
        overall_tool_started_at: float | None = None

        for _round in range(4):
            thinking_started_at = perf_counter()
            if emit is not None:
                emit(AgentStreamEvent(type="thinking_started", payload={"message": "正在分析当前问题"}))
            plan = self._extract_valid_action_plan(
                context=context,
                memory_key=memory_key,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
            )
            final_plan = plan
            if emit is not None:
                emit(
                    AgentStreamEvent(
                        type="thinking_completed",
                        payload={
                            "summary": _describe_plan_reason(plan.reason, plan),
                            "duration_ms": _elapsed_ms(thinking_started_at),
                        },
                    )
                )

            if not plan.tool_calls:
                if observed_tool_results and last_tool_plan is not None:
                    final_plan = last_tool_plan
                break

            if overall_tool_started_at is None:
                overall_tool_started_at = perf_counter()
            last_tool_plan = plan

            for call in plan.tool_calls:
                call_signature = call.model_dump_json(exclude_none=True)
                if call_signature in seen_calls:
                    raise RuntimeError("Agent 规划重复调用了相同工具，已中止本轮工具链。")
                seen_calls.add(call_signature)

                tool_started_at = perf_counter()
                if emit is not None:
                    emit(
                        AgentStreamEvent(
                            type="tool_started",
                            payload={
                                "tool_name": call.tool_name.value,
                            },
                        )
                    )
                result = self._tool_executor.execute_call(call, context)
                observed_tool_results.append(result)
                if emit is not None:
                    emit(
                        AgentStreamEvent(
                            type="tool_completed",
                            payload={
                                "tool_name": result.tool_name.value,
                                "status": result.status,
                                "payload": result.payload,
                                "duration_ms": _elapsed_ms(tool_started_at),
                            },
                        )
                    )
        else:
            raise RuntimeError("Agent 工具链规划超过最大轮数，已中止本轮对话。")

        if final_plan is None:
            raise RuntimeError("Agent 未能生成有效规划。")

        if emit is not None and overall_tool_started_at is not None:
            emit(
                AgentStreamEvent(
                    type="tool_chain_completed",
                    payload={
                        "count": len(observed_tool_results),
                        "duration_ms": _elapsed_ms(overall_tool_started_at),
                    },
                )
            )
        return final_plan, observed_tool_results

    def _extract_valid_action_plan(
        self,
        *,
        context: AgentContext,
        memory_key: str,
        user_message: str,
        observed_tool_results: list[ToolExecutionResult],
    ) -> AgentActionPlan:
        feedback = ""
        last_error = ""
        for _attempt in range(3):
            try:
                return extract_action_plan(
                    gateway=self._gateway,
                    context=context,
                    memory_store=self._memory_store,
                    session_id=memory_key,
                    user_message=user_message,
                    observed_tool_results=observed_tool_results,
                    planner_feedback=feedback,
                )
            except AgentPlanError as error:
                last_error = str(error)
                feedback = _build_retry_feedback(last_error)
        raise RuntimeError(f"Agent 无法生成有效工具规划：{last_error or '未知错误'}")


def _merge_context(base_context: AgentContext, context_override: AgentContext | None) -> AgentContext:
    if context_override is None:
        return base_context

    override_payload = context_override.model_dump(exclude_unset=True)
    override_payload.pop("session_id", None)
    return base_context.model_copy(update=override_payload)


def _build_memory_key(context: AgentContext, session_id: str) -> str:
    if context.scope_type == "library" or not context.series_id:
        return "library"
    return f"series|{context.series_id}"


def _attach_recent_messages(context: AgentContext, history: list[AgentChatMessage]) -> AgentContext:
    recent_messages = [message.content for message in history[-6:]]
    return context.model_copy(update={"recent_messages": recent_messages})


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _describe_plan_reason(reason: str, plan) -> str:
    if reason.strip():
        return reason.strip()
    if plan.tool_calls:
        return "先规划工具链，再基于工具结果生成最终回答。"
    return "当前问题不需要调用工具，直接组织回答。"


def _chunk_text(text: str, chunk_size: int = 14) -> Iterator[str]:
    normalized = text.strip()
    if not normalized:
        return
    for index in range(0, len(normalized), chunk_size):
        yield normalized[index:index + chunk_size]


def _build_retry_feedback(last_error: str) -> str:
    return (
        "上一次规划存在错误，请严格根据错误原因重新规划，不要重复相同错误。\n"
        f"{last_error}"
    )
