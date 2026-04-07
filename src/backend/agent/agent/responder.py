from __future__ import annotations

import json
from collections.abc import Iterator

from backend.agent.agent.prompt import build_agent_responder_prompt
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.responder_view import ResponderInputView, ResponderToolFact
from backend.agent.schemas.tool_calls import ToolExecutionResult


def generate_assistant_message(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
    plan: AgentActionPlan,
    tool_results: list[ToolExecutionResult],
) -> str:
    messages = build_responder_messages(
        context=context,
        memory_store=memory_store,
        session_id=session_id,
        user_message=user_message,
        plan=plan,
        tool_results=tool_results,
    )
    return gateway.create_text_completion(messages).strip()


def stream_assistant_message(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
    plan: AgentActionPlan,
    tool_results: list[ToolExecutionResult],
) -> Iterator[str]:
    messages = build_responder_messages(
        context=context,
        memory_store=memory_store,
        session_id=session_id,
        user_message=user_message,
        plan=plan,
        tool_results=tool_results,
    )
    return gateway.create_text_completion_stream(messages)


def build_responder_messages(
    *,
    context: AgentContext,
    memory_store: AgentMemoryStore,
    session_id: str,
    user_message: str,
    plan: AgentActionPlan,
    tool_results: list[ToolExecutionResult],
) -> list[AgentChatMessage]:
    history = memory_store.get_messages(session_id)
    return [
        AgentChatMessage(role="system", content=build_agent_responder_prompt(context)),
        *history[-6:],
        AgentChatMessage(role="user", content=_build_responder_user_message(user_message, plan, tool_results)),
    ]


def _build_responder_user_message(
    user_message: str,
    plan: AgentActionPlan,
    tool_results: list[ToolExecutionResult],
) -> str:
    view = _build_responder_input_view(user_message, plan, tool_results)
    return (
        "请基于下面信息，直接生成给用户看的最终回答。\n"
        "要求：\n"
        "1. 回答自然、像学习助手，不要提内部规划或实现细节。\n"
        "2. 可以使用 Markdown，让内容更清晰。\n"
        "3. 严格依据输入中的事实回答，不要编造不存在的信息。\n\n"
        f"{json.dumps(view.model_dump(mode='json'), ensure_ascii=False, indent=2)}"
    )


def _build_responder_input_view(
    user_message: str,
    plan: AgentActionPlan,
    tool_results: list[ToolExecutionResult],
) -> ResponderInputView:
    return ResponderInputView(
        user_message=user_message,
        answer_goal=_describe_answer_goal(plan),
        tool_facts=[_build_tool_fact(item) for item in tool_results],
    )


def _describe_answer_goal(plan: AgentActionPlan) -> str:
    if plan.intent_type.value == "seek_video":
        return "帮助用户定位当前内容在视频中的时间位置。"
    if plan.intent_type.value == "open_tool":
        return "根据用户请求切换到合适的工具页面，并自然说明结果。"
    if plan.intent_type.value == "generate_overview":
        return "告诉用户当前视频的 AI 概况已经开始生成，或说明生成结果。"
    if plan.intent_type.value == "generate_mindmap":
        return "告诉用户系统已经开始生成或完成生成导图。"
    if plan.intent_type.value == "series_answer":
        return "从整个系列的角度回答用户问题。"
    if plan.intent_type.value == "out_of_scope":
        return "礼貌说明当前问题超出工作台支持范围。"
    return "直接回答用户关于当前工作台内容的问题。"


def _build_tool_fact(result: ToolExecutionResult) -> ResponderToolFact:
    return ResponderToolFact(
        tool_name=result.tool_name.value,
        status=result.status,
        payload=dict(result.payload),
    )
