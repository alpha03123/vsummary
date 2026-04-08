from __future__ import annotations

import json

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.json_protocol import parse_json_completion
from backend.agent.schemas.action_plan import AgentActionPlan
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult
from backend.agent.tools import list_model_visible_tool_definitions_for_context


INITIAL_PLANNER_SYSTEM_PROMPT = (
    "你是视频知识工作台中的执行计划器。\n"
    "你的任务不是给问题贴标签，而是直接决定下一步该不该调用工具、调用哪些工具，或者是否已经可以直接回复。\n"
    "规则：\n"
    "1. 只能使用输入中提供的工具列表，绝对不要发明工具名。\n"
    "2. 如果还需要读取信息或执行动作，就填写 tool_calls。\n"
    "3. 如果已经拿到足够证据，应该交给回答器来组织自然回答，就设置 use_answerer=true，tool_calls 留空，direct_response 留空。\n"
    "4. 如果当前不需要工具也不需要回答器，例如问候、超范围拒绝、动作完成后的自然收口，请直接填写 direct_response。\n"
    "5. direct_response 必须是自然中文回复，不要暴露 tool_name、payload、schema、规划这些内部实现词。\n"
    "6. tool_calls、direct_response、use_answerer 三者只能激活一种：\n"
    "   - 要继续工作：tool_calls 非空\n"
    "   - 要直接回复：direct_response 非空\n"
    "   - 要基于现有证据回答：use_answerer=true\n"
    "7. 如果用户请求混合多个动作，可以在同一轮输出多个 tool_calls。\n"
    "8. 只输出 JSON，不要输出代码块，不要解释。\n"
    '9. JSON 格式固定为 {"scope_type":"series或video","tool_calls":[...],"reason":"...","direct_response":"...","use_answerer":true或false}。\n'
)


def generate_execution_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
) -> AgentActionPlan:
    messages = [
        AgentChatMessage(role="system", content=INITIAL_PLANNER_SYSTEM_PROMPT),
        AgentChatMessage(
            role="user",
            content=json.dumps(
                {
                    "user_message": user_message,
                    "context": {
                        "scope_type": context.scope_type,
                        "series_id": context.series_id,
                        "series_title": context.series_title,
                        "video_id": context.video_id,
                        "video_title": context.video_title,
                        "selected_tool": context.selected_tool,
                        "overview": _dump_tool_state(context.overview),
                        "mindmap": _dump_tool_state(context.mindmap),
                        "knowledge_cards": _dump_tool_state(context.knowledge_cards),
                        "notes": _dump_tool_state(context.notes),
                        "preview": _dump_tool_state(context.preview),
                        "recent_messages": context.recent_messages,
                    },
                    "available_tools": [
                        {
                            "name": tool.name.value,
                            "title": tool.title,
                            "description": tool.description,
                            "arguments": tool.arguments,
                        }
                        for tool in list_model_visible_tool_definitions_for_context(context)
                    ],
                    "observed_tool_results": [
                        {
                            "tool_name": result.tool_name.value,
                            "status": result.status,
                            "payload": result.payload,
                        }
                        for result in observed_tool_results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    raw_output = gateway.create_text_completion(messages).strip()
    return parse_json_completion(raw_output, AgentActionPlan)


def _dump_tool_state(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return {}
