from __future__ import annotations

import json

from pydantic import TypeAdapter

from backend.agent.agent.prompt import build_agent_planner_prompt
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan, PlannerActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult
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
    planner_plan = gateway.create_structured_completion(messages, PlannerActionPlan)
    plan = _convert_planner_plan(planner_plan)
    return validate_action_plan(plan, observed_results)


def _convert_planner_plan(planner_plan: PlannerActionPlan) -> AgentActionPlan:
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
        reason=planner_plan.reason,
        out_of_scope_reason=planner_plan.out_of_scope_reason,
    )


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
