from __future__ import annotations

import json

from backend.agent.agent.prompt import build_agent_responder_prompt
from backend.agent.memory.context import AgentContext
from backend.agent.memory.store import AgentMemoryStore
from backend.agent.ports import ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.responder_view import ResponderFact, ResponderInputView, ResponderToolFact
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
    history = memory_store.get_messages(session_id)
    messages = [
        AgentChatMessage(role="system", content=build_agent_responder_prompt(context)),
        *history[-6:],
        AgentChatMessage(role="user", content=_build_responder_user_message(user_message, plan, tool_results)),
    ]
    return gateway.create_text_completion(messages).strip()


def _build_responder_user_message(
    user_message: str,
    plan: AgentActionPlan,
    tool_results: list[ToolExecutionResult],
) -> str:
    view = _build_responder_input_view(user_message, plan, tool_results)
    return (
        "请基于下面信息，直接生成给用户看的最终回答。\n"
        "要求：\n"
        "1. 回答自然、像学习助手，不要提内部规划、JSON、schema、tool_calls。\n"
        "2. 可以使用 Markdown，让内容更清晰。\n"
        "3. 如果事实里已经定位到时间点，就自然告诉用户，并引导他查看对应工具。\n"
        "4. 不要编造工具结果中没有的信息。\n\n"
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
        return "告诉用户系统已经开始生成或完成生成概况。"
    if plan.intent_type.value == "generate_mindmap":
        return "告诉用户系统已经开始生成或完成生成导图。"
    if plan.intent_type.value == "series_answer":
        return "从整个系列的角度回答用户问题。"
    if plan.intent_type.value == "out_of_scope":
        return "礼貌说明当前问题超出工作台支持范围。"
    return "直接回答用户关于当前工作台内容的问题。"


def _build_tool_fact(result: ToolExecutionResult) -> ResponderToolFact:
    payload = _sanitize_payload(result.payload)
    facts: list[ResponderFact] = []

    selected_tool = payload.get("selected_tool")
    if isinstance(selected_tool, str) and selected_tool.strip():
        facts.append(ResponderFact(kind="selected_tool", value=selected_tool))

    seek_seconds = payload.get("seek_seconds")
    if isinstance(seek_seconds, (int, float)):
        facts.append(ResponderFact(kind="seek_seconds", value=f"{float(seek_seconds):.2f}"))

    match_end_seconds = payload.get("match_end_seconds")
    if isinstance(match_end_seconds, (int, float)):
        facts.append(ResponderFact(kind="match_end_seconds", value=f"{float(match_end_seconds):.2f}"))

    query = payload.get("query")
    if isinstance(query, str) and query.strip():
        facts.append(ResponderFact(kind="query", value=query))

    matched_text = payload.get("matched_text")
    if isinstance(matched_text, str) and matched_text.strip():
        facts.append(ResponderFact(kind="matched_text", value=matched_text))

    chapter_title = payload.get("chapter_title")
    if isinstance(chapter_title, str) and chapter_title.strip():
        facts.append(ResponderFact(kind="chapter_title", value=chapter_title))

    action = payload.get("action")
    if isinstance(action, str) and action.strip():
        facts.append(ResponderFact(kind="action", value=action))

    return ResponderToolFact(
        tool_name=result.tool_name.value,
        status=result.status,
        facts=facts,
        payload=payload,
    )


def _sanitize_payload(payload: dict[str, object]) -> dict[str, object]:
    allowed_keys = {
        "series_id",
        "series_title",
        "video_id",
        "title",
        "generated",
        "one_sentence_summary",
        "core_problem",
        "key_takeaways",
        "chapters",
        "videos",
        "overview",
        "knowledge_cards",
        "mindmap",
        "notes",
        "preview",
        "selected_tool",
        "seek_seconds",
        "match_end_seconds",
        "query",
        "matched_text",
        "chapter_title",
        "action",
        "note_title",
        "note_content",
    }
    return {key: value for key, value in payload.items() if key in allowed_keys}
