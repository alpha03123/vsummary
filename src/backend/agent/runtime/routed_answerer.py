from __future__ import annotations

import json
from collections.abc import Iterator

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.prompt_projection import build_prompt_projection
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult


ROUTED_ANSWERER_SYSTEM_PROMPT = (
    "你是视频知识工作台中的轻量回答器。\n"
    "你不会规划工具，只负责基于已经拿到的证据，尽快给用户一个自然、可信、可读的最终回答。\n"
    "规则：\n"
    "1. 只能依据输入中的证据回答，不要补写未知事实。\n"
    "2. 如果证据不完整，要明确说是当前已知范围内的概括或初步判断。\n"
    "3. 不要提工具名、payload、规划、路由、schema 这些内部实现词。\n"
    "4. 可以使用 Markdown，让结果更清晰。\n"
    "5. series 问题优先做跨视频归纳；video 问题优先围绕当前视频回答。\n"
    "6. 如果证据显示内容缺失或未生成，要直接说明缺口，不要假装已经读到内容。\n"
)


def generate_routed_assistant_message(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    tool_results: list[ToolExecutionResult],
    projection_max_tokens: int | None = None,
) -> str:
    messages = build_routed_answer_messages(
        context=context,
        user_message=user_message,
        tool_results=tool_results,
        projection_max_tokens=projection_max_tokens,
    )
    return gateway.create_text_completion(messages).strip()


def stream_routed_assistant_message(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    tool_results: list[ToolExecutionResult],
    projection_max_tokens: int | None = None,
) -> Iterator[str]:
    messages = build_routed_answer_messages(
        context=context,
        user_message=user_message,
        tool_results=tool_results,
        projection_max_tokens=projection_max_tokens,
    )
    return gateway.create_text_completion_stream(messages)


def build_routed_answer_messages(
    *,
    context: AgentContext,
    user_message: str,
    tool_results: list[ToolExecutionResult],
    projection_max_tokens: int | None = None,
) -> list[AgentChatMessage]:
    payload = build_prompt_projection(
        context=context,
        user_message=user_message,
        tool_results=tool_results,
        max_tokens=projection_max_tokens,
    )
    return [
        AgentChatMessage(role="system", content=ROUTED_ANSWERER_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
        ),
    ]
