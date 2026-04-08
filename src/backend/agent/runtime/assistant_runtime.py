from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from time import perf_counter

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentToolExecutor, ChatGateway
from backend.agent.runtime.evidence_policy import build_followup_plan
from backend.agent.runtime.lanes import (
    build_deterministic_assistant_message,
    build_initial_route_plan,
    build_save_note_followup_plan,
    build_seek_followup_plan,
    build_series_locate_followup_plan,
)
from backend.agent.runtime.routed_answerer import generate_routed_assistant_message, stream_routed_assistant_message
from backend.agent.session.evidence_cache import build_cached_result_index, build_result_cache_key, filter_cached_tool_calls
from backend.agent.runtime.tool_loop import (
    apply_tool_result_to_context,
    execute_tool_batch,
    finalize_context_after_turn,
    partition_tool_calls,
)
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.stream_events import AgentStreamEvent
from backend.agent.schemas.tool_calls import ToolExecutionResult


@dataclass(frozen=True)
class RuntimeExecutionResult:
    context: AgentContext
    assistant_message: str
    plan: AgentActionPlan
    tool_results: list[ToolExecutionResult]


class AssistantRuntime:
    def __init__(
        self,
        *,
        gateway: ChatGateway,
        tool_executor: AgentToolExecutor,
        projection_max_tokens: int | None = None,
    ) -> None:
        self._gateway = gateway
        self._tool_executor = tool_executor
        self._projection_max_tokens = projection_max_tokens

    def run(
        self,
        *,
        context: AgentContext,
        memory_key: str,
        user_message: str,
        cached_tool_results: list[ToolExecutionResult],
    ) -> RuntimeExecutionResult:
        del memory_key
        initial_plan = build_initial_route_plan(
            gateway=self._gateway,
            context=context,
            user_message=user_message,
            observed_tool_results=[],
            last_tool_plan=None,
        )
        context, plan, tool_results = self._run_routed_loop(
            context=context,
            initial_plan=initial_plan,
            user_message=user_message,
            cached_tool_results=cached_tool_results,
        )

        assistant_message = build_deterministic_assistant_message(plan, tool_results)
        if assistant_message is None:
            assistant_message = generate_routed_assistant_message(
                gateway=self._gateway,
                context=context,
                user_message=user_message,
                plan=plan,
                tool_results=tool_results,
                projection_max_tokens=self._projection_max_tokens,
            )
        return RuntimeExecutionResult(
            context=context,
            assistant_message=assistant_message,
            plan=plan,
            tool_results=tool_results,
        )

    def stream(
        self,
        *,
        context: AgentContext,
        memory_key: str,
        user_message: str,
        cached_tool_results: list[ToolExecutionResult],
    ) -> Iterator[AgentStreamEvent]:
        del memory_key
        initial_plan = build_initial_route_plan(
            gateway=self._gateway,
            context=context,
            user_message=user_message,
            observed_tool_results=[],
            last_tool_plan=None,
        )
        runtime_stream = self._stream_routed_loop(
            context=context,
            initial_plan=initial_plan,
            user_message=user_message,
            cached_tool_results=cached_tool_results,
        )

        while True:
            try:
                event = next(runtime_stream)
            except StopIteration as completed:
                context, plan, tool_results = completed.value
                break
            yield event

        assistant_message = build_deterministic_assistant_message(plan, tool_results)
        if assistant_message is None:
            answer_started_at = perf_counter()
            yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
            chunks: list[str] = []
            for delta in stream_routed_assistant_message(
                gateway=self._gateway,
                context=context,
                user_message=user_message,
                plan=plan,
                tool_results=tool_results,
                projection_max_tokens=self._projection_max_tokens,
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
        else:
            answer_started_at = perf_counter()
            yield AgentStreamEvent(type="answer_started", payload={"message": "正在返回执行结果"})
            yield AgentStreamEvent(type="answer_delta", payload={"delta": assistant_message})
            yield AgentStreamEvent(
                type="answer_completed",
                payload={
                    "message": assistant_message,
                    "duration_ms": _elapsed_ms(answer_started_at),
                },
            )

        return RuntimeExecutionResult(
            context=context,
            assistant_message=assistant_message,
            plan=plan,
            tool_results=tool_results,
        )

    def _run_routed_loop(
        self,
        *,
        context: AgentContext,
        initial_plan: AgentActionPlan,
        user_message: str,
        cached_tool_results: list[ToolExecutionResult],
    ) -> tuple[AgentContext, AgentActionPlan, list[ToolExecutionResult]]:
        observed_tool_results: list[ToolExecutionResult] = list(cached_tool_results)
        cached_result_index = build_cached_result_index(cached_tool_results)
        final_plan = initial_plan
        current_plan = initial_plan

        while True:
            for batch in partition_tool_calls(current_plan.tool_calls):
                executable_calls = filter_cached_tool_calls(
                    batch,
                    context=context,
                    cached_index=cached_result_index,
                )
                if not executable_calls:
                    continue
                results = execute_tool_batch(
                    tool_executor=self._tool_executor,
                    calls=executable_calls,
                    context=context,
                )
                for result in results:
                    observed_tool_results.append(result)
                    cache_key = build_result_cache_key(result)
                    if cache_key is not None:
                        cached_result_index[cache_key] = result
                    context = apply_tool_result_to_context(context, result)

            final_plan = current_plan
            next_plan = self._build_followup_plan(
                context=context,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
                last_tool_plan=current_plan,
            )
            if next_plan is None:
                break
            current_plan = next_plan

        return finalize_context_after_turn(context, observed_tool_results), final_plan, observed_tool_results

    def _stream_routed_loop(
        self,
        *,
        context: AgentContext,
        initial_plan: AgentActionPlan,
        user_message: str,
        cached_tool_results: list[ToolExecutionResult],
    ) -> Iterator[AgentStreamEvent]:
        observed_tool_results: list[ToolExecutionResult] = list(cached_tool_results)
        cached_result_index = build_cached_result_index(cached_tool_results)
        final_plan = initial_plan
        current_plan = initial_plan
        overall_tool_started_at = perf_counter()
        tool_event_index = 0
        emitted_thinking_for_route = False

        while True:
            if not emitted_thinking_for_route:
                thinking_started_at = perf_counter()
                yield AgentStreamEvent(type="thinking_started", payload={"message": "正在分析当前问题"})
                yield AgentStreamEvent(
                    type="thinking_completed",
                    payload={
                        "summary": _describe_plan_reason(current_plan.reason, current_plan),
                        "duration_ms": _elapsed_ms(thinking_started_at),
                    },
                )
                emitted_thinking_for_route = True

            for batch in partition_tool_calls(current_plan.tool_calls):
                executable_calls = filter_cached_tool_calls(
                    batch,
                    context=context,
                    cached_index=cached_result_index,
                )
                if not executable_calls:
                    continue
                batch_started_at = [perf_counter() for _ in executable_calls]
                batch_tool_call_ids: list[str] = []
                for call in executable_calls:
                    tool_event_index += 1
                    tool_call_id = f"tool-{tool_event_index}"
                    batch_tool_call_ids.append(tool_call_id)
                    yield AgentStreamEvent(
                        type="tool_started",
                        payload={
                            "tool_call_id": tool_call_id,
                            "tool_name": call.tool_name.value,
                            "index": tool_event_index,
                        },
                    )
                results = execute_tool_batch(
                    tool_executor=self._tool_executor,
                    calls=executable_calls,
                    context=context,
                )
                for index, result in enumerate(results):
                    observed_tool_results.append(result)
                    cache_key = build_result_cache_key(result)
                    if cache_key is not None:
                        cached_result_index[cache_key] = result
                    context = apply_tool_result_to_context(context, result)
                    yield AgentStreamEvent(
                        type="tool_completed",
                        payload={
                            "tool_call_id": batch_tool_call_ids[index],
                            "tool_name": result.tool_name.value,
                            "status": result.status,
                            "payload": result.payload,
                            "duration_ms": _elapsed_ms(batch_started_at[index]),
                        },
                    )

            final_plan = current_plan
            next_plan = self._build_followup_plan(
                context=context,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
                last_tool_plan=current_plan,
            )
            if next_plan is None:
                break
            current_plan = next_plan

        if observed_tool_results:
            yield AgentStreamEvent(
                type="tool_chain_completed",
                payload={
                    "count": len(observed_tool_results),
                    "duration_ms": _elapsed_ms(overall_tool_started_at),
                },
            )
        return finalize_context_after_turn(context, observed_tool_results), final_plan, observed_tool_results

    def _build_followup_plan(
        self,
        *,
        context: AgentContext,
        user_message: str,
        observed_tool_results: list[ToolExecutionResult],
        last_tool_plan: AgentActionPlan,
    ) -> AgentActionPlan | None:
        next_plan = build_seek_followup_plan(
            gateway=self._gateway,
            user_message=user_message,
            observed_tool_results=observed_tool_results,
            last_tool_plan=last_tool_plan,
        )
        if next_plan is not None:
            return next_plan

        next_plan = build_series_locate_followup_plan(
            gateway=self._gateway,
            user_message=user_message,
            observed_tool_results=observed_tool_results,
            last_tool_plan=last_tool_plan,
        )
        if next_plan is not None:
            return next_plan

        next_plan = build_save_note_followup_plan(
            gateway=self._gateway,
            context=context,
            user_message=user_message,
            observed_tool_results=observed_tool_results,
            last_tool_plan=last_tool_plan,
        )
        if next_plan is not None:
            return next_plan

        return build_followup_plan(
            context=context,
            observed_tool_results=observed_tool_results,
            last_tool_plan=last_tool_plan,
        )


def _describe_plan_reason(reason: str, plan: AgentActionPlan) -> str:
    if reason.strip():
        return reason.strip()
    if plan.tool_calls:
        return "先执行工具链，再基于工具结果生成最终回答。"
    return "当前问题不需要调用工具，直接组织回答。"


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))
