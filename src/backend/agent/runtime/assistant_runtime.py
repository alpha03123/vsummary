from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from time import perf_counter

from backend.agent.memory.context import AgentContext
from backend.agent.ports import AgentToolExecutor, ChatGateway
from backend.agent.runtime.planner import generate_execution_plan
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
from backend.agent.validation.plan import validate_action_plan


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
        initial_plan = self._generate_valid_plan(
            context=context,
            user_message=user_message,
            observed_tool_results=cached_tool_results,
        )
        context, plan, tool_results = self._run_routed_loop(
            context=context,
            initial_plan=initial_plan,
            user_message=user_message,
            cached_tool_results=cached_tool_results,
        )

        assistant_message = plan.direct_response.strip()
        if not assistant_message:
            assistant_message = generate_routed_assistant_message(
                gateway=self._gateway,
                context=context,
                user_message=user_message,
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
        initial_plan = self._generate_valid_plan(
            context=context,
            user_message=user_message,
            observed_tool_results=cached_tool_results,
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

        assistant_message = plan.direct_response.strip()
        if not assistant_message:
            answer_started_at = perf_counter()
            yield AgentStreamEvent(type="answer_started", payload={"message": "正在组织回答"})
            chunks: list[str] = []
            for delta in stream_routed_assistant_message(
                gateway=self._gateway,
                context=context,
                user_message=user_message,
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
        planning_round = 0

        while True:
            planning_round += 1
            if planning_round > 8:
                raise RuntimeError("Agent 计划轮次过多，可能出现了无法收敛的循环。")
            if current_plan.direct_response.strip() or current_plan.use_answerer:
                final_plan = current_plan
                break
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
            current_plan = self._generate_valid_plan(
                context=context,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
            )

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
        planning_round = 0

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

            planning_round += 1
            if planning_round > 8:
                raise RuntimeError("Agent 计划轮次过多，可能出现了无法收敛的循环。")
            if current_plan.direct_response.strip() or current_plan.use_answerer:
                final_plan = current_plan
                break

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
            current_plan = self._generate_valid_plan(
                context=context,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
            )

        if observed_tool_results:
            yield AgentStreamEvent(
                type="tool_chain_completed",
                payload={
                    "count": len(observed_tool_results),
                    "duration_ms": _elapsed_ms(overall_tool_started_at),
                },
        )
        return finalize_context_after_turn(context, observed_tool_results), final_plan, observed_tool_results

    def _generate_valid_plan(
        self,
        *,
        context: AgentContext,
        user_message: str,
        observed_tool_results: list[ToolExecutionResult],
    ) -> AgentActionPlan:
        validation_error: str | None = None
        for attempt in range(3):
            plan = generate_execution_plan(
                gateway=self._gateway,
                context=context,
                user_message=user_message,
                observed_tool_results=observed_tool_results,
                validation_error=validation_error,
            )
            try:
                return validate_action_plan(plan, context, observed_tool_results)
            except Exception as error:
                validation_error = str(error)
                if attempt == 2:
                    raise
        raise RuntimeError("未能生成有效计划。")

def _describe_plan_reason(reason: str, plan: AgentActionPlan) -> str:
    if reason.strip():
        return reason.strip()
    if plan.tool_calls:
        return "先执行工具链，再基于工具结果生成最终回答。"
    if plan.direct_response.strip():
        return "当前不需要继续调用工具，直接给出自然回复。"
    return "当前问题不需要调用工具，直接组织回答。"


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))
