from __future__ import annotations

import json
from collections.abc import Iterator

from pydantic import TypeAdapter

from backend.agent.agent.prompt import PLANNER_SENTINEL, build_agent_planner_prompt
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan, PlannerActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult
from backend.agent.validation.errors import AgentPlanError
from backend.agent.validation.plan import validate_action_plan


def extract_action_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult] | None = None,
    planner_feedback: str = "",
) -> AgentActionPlan:
    thinking_summary, planner_plan = _request_planner_plan(
        gateway=gateway,
        context=context,
        memory_store=memory_store,
        session_id=session_id,
        user_message=user_message,
        observed_tool_results=observed_tool_results,
        planner_feedback=planner_feedback,
    )
    plan = _convert_planner_plan(planner_plan, thinking_summary)
    return validate_action_plan(
        plan,
        context,
        observed_tool_results or [],
    )


def stream_action_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult] | None = None,
    planner_feedback: str = "",
    ) -> Iterator[str]:
    thinking_summary, planner_plan = yield from _request_planner_plan_stream(
        gateway=gateway,
        context=context,
        memory_store=memory_store,
        session_id=session_id,
        user_message=user_message,
        observed_tool_results=observed_tool_results,
        planner_feedback=planner_feedback,
    )
    plan = _convert_planner_plan(planner_plan, thinking_summary)
    return validate_action_plan(
        plan,
        context,
        observed_tool_results or [],
    )


def _request_planner_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult] | None = None,
    planner_feedback: str = "",
) -> tuple[str, PlannerActionPlan]:
    observed_results = observed_tool_results or []
    history = memory_store.get_messages(session_id)
    messages = [
        AgentChatMessage(role="system", content=build_agent_planner_prompt(context)),
        *history,
        AgentChatMessage(
            role="user",
            content=_build_planner_user_message(user_message, observed_results, planner_feedback),
        ),
    ]
    completion = gateway.create_text_completion(messages)
    return _parse_planner_completion(completion)

def _request_planner_plan_stream(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult] | None = None,
    planner_feedback: str = "",
) -> Iterator[str]:
    observed_results = observed_tool_results or []
    history = memory_store.get_messages(session_id)
    messages = [
        AgentChatMessage(role="system", content=build_agent_planner_prompt(context)),
        *history,
        AgentChatMessage(
            role="user",
            content=_build_planner_user_message(user_message, observed_results, planner_feedback),
        ),
    ]

    buffer = ""
    emitted_thinking = ""
    for chunk in gateway.create_text_completion_stream(messages):
        if not chunk:
            continue
        buffer += chunk
        visible_thinking = _extract_streaming_thinking(buffer)
        if len(visible_thinking) > len(emitted_thinking):
            yield visible_thinking[len(emitted_thinking):]
        emitted_thinking = visible_thinking

    thinking_summary, planner_plan = _parse_planner_completion(buffer)
    if len(thinking_summary) > len(emitted_thinking):
        yield thinking_summary[len(emitted_thinking):]
    return thinking_summary, planner_plan


def _convert_planner_plan(planner_plan: PlannerActionPlan, thinking_summary: str) -> AgentActionPlan:
    tool_call_adapter = TypeAdapter(ToolCall)
    tool_calls = [
        tool_call_adapter.validate_python(
            call.model_dump(exclude_none=True),
        )
        for call in planner_plan.tool_calls
    ]
    return AgentActionPlan(
        intent_type=planner_plan.intent_type,
        scope_type=planner_plan.scope_type,
        assistant_message=planner_plan.assistant_message,
        tool_calls=tool_calls,
        reason=thinking_summary or planner_plan.reason,
        out_of_scope_reason=planner_plan.out_of_scope_reason,
    )


def _parse_planner_completion(completion: str) -> tuple[str, PlannerActionPlan]:
    marker_index = completion.find(PLANNER_SENTINEL)
    if marker_index < 0:
        raise AgentPlanError("Planner 输出缺少固定标记 <<PLAN>>。")

    thinking_summary = completion[:marker_index].strip()
    raw_plan = completion[marker_index + len(PLANNER_SENTINEL):].strip()
    plan_text = _strip_optional_code_fence(raw_plan)
    if not plan_text:
        raise AgentPlanError("Planner 输出缺少 JSON 计划。")
    try:
        planner_plan = PlannerActionPlan.model_validate_json(plan_text)
    except Exception as error:
        raise AgentPlanError(f"Planner JSON 无法解析：{error}") from error
    return thinking_summary, planner_plan


def _strip_optional_code_fence(text: str) -> str:
    normalized = text.strip()
    if not normalized.startswith("```"):
        return normalized
    lines = normalized.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return normalized


def _extract_streaming_thinking(buffer: str) -> str:
    marker_index = buffer.find(PLANNER_SENTINEL)
    if marker_index >= 0:
        return buffer[:marker_index].rstrip()
    return _trim_partial_marker_suffix(buffer, PLANNER_SENTINEL).rstrip()


def _trim_partial_marker_suffix(text: str, marker: str) -> str:
    for prefix_length in range(len(marker) - 1, 0, -1):
        if text.endswith(marker[:prefix_length]):
            return text[:-prefix_length]
    return text


def _build_planner_user_message(
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
    planner_feedback: str,
) -> str:
    feedback_block = ""
    if planner_feedback.strip():
        feedback_block = (
            "上一次规划存在错误，请严格修正后再输出新的结构化规划：\n"
            f"{planner_feedback.strip()}\n\n"
        )
    if not observed_tool_results:
        return f"{feedback_block}{user_message}" if feedback_block else user_message
    return (
        f"用户原始问题：{user_message}\n\n"
        f"{feedback_block}"
        "下面是本轮已经观察到的工具结果。请基于这些事实决定下一步。"
        "如果信息已经足够，请不要重复调用同样的工具。\n"
        f"{json.dumps([_serialize_tool_result(item) for item in observed_tool_results], ensure_ascii=False, indent=2)}"
    )


def _serialize_tool_result(result: ToolExecutionResult) -> dict[str, object]:
    return {
        "tool_name": result.tool_name.value,
        "status": result.status,
        "payload": result.payload,
    }
