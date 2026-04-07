from __future__ import annotations

from collections.abc import Iterator
from time import perf_counter
from typing import Callable

from backend.agent.agent.planner import extract_action_plan, stream_action_plan
from backend.agent.context.compact import AgentMemoryCompactionService
from backend.agent.agent.responder import generate_assistant_message, stream_assistant_message
from backend.agent.agent.execution import RegistryAgentToolExecutor
from backend.agent.memory.context import AgentContext, CandidateBufferEntry, InspectionStage
from backend.agent.memory.runtime import load_runtime_context
from backend.agent.memory.store import AgentMemoryStore, InMemoryAgentMemoryStore
from backend.agent.ports import AgentContextLoader, AgentSessionStore, AgentToolExecutor, ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan, AgentTurnResult
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent.schemas.tool_calls import ToolEffectTag, ToolExecutionResult
from backend.agent.tools import tool_has_effect
from backend.agent.validation.errors import AgentPlanError

MAX_PLANNING_ROUNDS = 6


class AgentService:
    def __init__(
        self,
        gateway: ChatGateway,
        context_loader: AgentContextLoader,
        memory_store: AgentMemoryStore | None = None,
        session_store: AgentSessionStore | None = None,
        memory_compaction_service: AgentMemoryCompactionService | None = None,
        tool_executor: AgentToolExecutor | None = None,
    ) -> None:
        self._gateway = gateway
        self._context_loader = context_loader
        self._memory_store = memory_store or InMemoryAgentMemoryStore()
        self._session_store = session_store
        self._memory_compaction_service = memory_compaction_service
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
        self._compact_memory_if_needed(session_id, context_override)
        context, memory_key = self._load_runtime_context(session_id, context_override)
        context, plan, tool_results = self._run_planning_loop(
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
        self._record_session_turn(
            session_id=session_id,
            memory_key=memory_key,
            context=context,
            user_message=user_message,
            assistant_message=assistant_message,
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
        self._compact_memory_if_needed(session_id, context_override)
        context, memory_key = self._load_runtime_context(session_id, context_override)
        context, plan, tool_results = yield from self._stream_planning_loop(
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
        self._record_session_turn(
            session_id=session_id,
            memory_key=memory_key,
            context=context,
            user_message=user_message,
            assistant_message=assistant_message,
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

        for _round in range(MAX_PLANNING_ROUNDS):
            thinking_started_at = perf_counter()
            yield AgentStreamEvent(type="thinking_started", payload={"message": "正在分析当前问题"})
            streamed_reason_parts: list[str] = []
            plan = yield from self._extract_valid_action_plan_stream(
                context=context,
                memory_key=memory_key,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
                streamed_reason_parts=streamed_reason_parts,
            )
            final_plan = plan
            reasoning_summary = "".join(streamed_reason_parts).strip() or _describe_plan_reason(plan.reason, plan)
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
                context = _apply_tool_result_to_context(context, result)
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

        return context, final_plan, observed_tool_results

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

    def _run_planning_loop(
        self,
        *,
        context: AgentContext,
        memory_key: str,
        user_message: str,
        emit: Callable[[AgentStreamEvent], None] | None = None,
    ) -> tuple[AgentContext, AgentActionPlan, list[ToolExecutionResult]]:
        observed_tool_results: list[ToolExecutionResult] = []
        final_plan: AgentActionPlan | None = None
        last_tool_plan: AgentActionPlan | None = None
        seen_calls: set[str] = set()
        overall_tool_started_at: float | None = None

        for _round in range(MAX_PLANNING_ROUNDS):
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
                context = _apply_tool_result_to_context(context, result)
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
        return context, final_plan, observed_tool_results

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

    def _extract_valid_action_plan_stream(
        self,
        *,
        context: AgentContext,
        memory_key: str,
        user_message: str,
        observed_tool_results: list[ToolExecutionResult],
        streamed_reason_parts: list[str],
    ) -> Iterator[AgentStreamEvent]:
        feedback = ""
        last_error = ""
        for _attempt in range(3):
            try:
                planner_stream = stream_action_plan(
                    gateway=self._gateway,
                    context=context,
                    memory_store=self._memory_store,
                    session_id=memory_key,
                    user_message=user_message,
                    observed_tool_results=observed_tool_results,
                    planner_feedback=feedback,
                )
                while True:
                    try:
                        delta = next(planner_stream)
                    except StopIteration as completed:
                        return completed.value
                    if delta:
                        streamed_reason_parts.append(delta)
                        yield AgentStreamEvent(type="thinking_delta", payload={"delta": delta})
            except AgentPlanError as error:
                last_error = str(error)
                feedback = _build_retry_feedback(last_error)
                if streamed_reason_parts:
                    streamed_reason_parts.append("\n")
                    yield AgentStreamEvent(type="thinking_delta", payload={"delta": "\n"})
        raise RuntimeError(f"Agent 无法生成有效工具规划：{last_error or '未知错误'}")

    def _record_session_turn(
        self,
        *,
        session_id: str,
        memory_key: str,
        context: AgentContext,
        user_message: str,
        assistant_message: str,
    ) -> None:
        if self._session_store is None:
            return
        self._session_store.append_turn(
            session_id=session_id,
            memory_key=memory_key,
            context=context,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    def _compact_memory_if_needed(self, session_id: str, context_override: AgentContext | None) -> None:
        if self._memory_compaction_service is None:
            return
        context, memory_key = self._load_runtime_context(session_id, context_override)
        del context
        self._memory_compaction_service.compact_if_needed(memory_key)

def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _describe_plan_reason(reason: str, plan) -> str:
    if reason.strip():
        return reason.strip()
    if plan.tool_calls:
        return "先规划工具链，再基于工具结果生成最终回答。"
    return "当前问题不需要调用工具，直接组织回答。"


def _build_retry_feedback(last_error: str) -> str:
    return (
        "上一次规划存在错误，请严格根据错误原因重新规划，不要重复相同错误。\n"
        "如果错误来自 intent_type 与 tool_calls 不匹配，先修正意图分类，再选择该意图允许的工具。\n"
        f"{last_error}"
    )


def _apply_tool_result_to_context(context: AgentContext, result: ToolExecutionResult) -> AgentContext:
    payload = result.payload
    next_context = _apply_selected_tool_payload(context, payload)
    if tool_has_effect(result.tool_name, ToolEffectTag.APPLY_CANDIDATE_BUFFER_PAYLOAD):
        return _apply_candidate_buffer_payload(next_context, payload)
    if tool_has_effect(result.tool_name, ToolEffectTag.MARK_VIDEO_INSPECTED):
        return _mark_video_as_inspected(next_context, payload.get("video_id"))
    return next_context


def _apply_selected_tool_payload(context: AgentContext, payload: dict[str, object]) -> AgentContext:
    selected_tool = payload.get("selected_tool")
    if not isinstance(selected_tool, str) or not selected_tool.strip():
        return context
    return context.model_copy(update={"selected_tool": selected_tool.strip()})


def _apply_candidate_buffer_payload(context: AgentContext, payload: dict[str, object]) -> AgentContext:
    raw_buffer = payload.get("candidate_buffer")
    next_buffer = context.candidate_buffer
    if isinstance(raw_buffer, list):
        next_buffer = [
            CandidateBufferEntry.model_validate(item)
            for item in raw_buffer
            if isinstance(item, dict)
        ]
    inspected_video_ids = context.inspected_video_ids
    rejected_video_ids = context.rejected_video_ids
    raw_inspected = payload.get("inspected_video_ids")
    if isinstance(raw_inspected, list):
        inspected_video_ids = [str(item).strip() for item in raw_inspected if str(item).strip()]
    raw_rejected = payload.get("rejected_video_ids")
    if isinstance(raw_rejected, list):
        rejected_video_ids = [str(item).strip() for item in raw_rejected if str(item).strip()]
    next_stage = InspectionStage.VIDEO_INSPECTION if next_buffer else InspectionStage.SERIES_DISCOVERY
    return context.model_copy(
        update={
            "candidate_buffer": next_buffer,
            "inspected_video_ids": inspected_video_ids,
            "rejected_video_ids": rejected_video_ids,
            "inspection_stage": next_stage,
        }
    )


def _mark_video_as_inspected(context: AgentContext, video_id: object) -> AgentContext:
    if not isinstance(video_id, str) or not video_id.strip():
        return context
    normalized_video_id = video_id.strip()
    inspected_video_ids = list(context.inspected_video_ids)
    if normalized_video_id not in inspected_video_ids:
        inspected_video_ids.append(normalized_video_id)
    return context.model_copy(
        update={
            "inspected_video_ids": inspected_video_ids,
            "inspection_stage": InspectionStage.ANSWER_READY,
        }
    )
