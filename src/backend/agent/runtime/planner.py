from __future__ import annotations

import json
from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.schemas.action_plan import AgentActionPlan, ScopeType
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName
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
    "8. 在 series 上下文里，get_video_summary / get_video_transcript / get_video_tools 这类深层读取工具必须带明确 video_id；如果当前还无法确定 video_id，就不要调用这些工具，而是先 list_series_videos，或者直接用 direct_response 说明需要用户进一步明确。\n"
    "9. open_* / generate_* / save_note 这类动作工具，只有当用户明确要求打开、生成、记录时才调用；普通问答不要调用页面切换工具。\n"
    "10. 只输出 JSON，不要输出代码块，不要解释。\n"
    '11. JSON 格式固定为 {"scope_type":"series或video","tool_calls":[...],"reason":"...","direct_response":"...","use_answerer":true或false}。\n'
)


class PlannedToolCall(BaseModel):
    name: ToolName
    series_id: str | None = None
    video_id: str | None = None
    video_ids: list[str] = Field(default_factory=list)
    seek_seconds: float | None = None
    match_end_seconds: float | None = None
    matched_text: str = ""
    chapter_title: str = ""
    query: str = ""
    note_title: str = ""
    note_content: str = ""


class PlannerOutput(BaseModel):
    scope_type: ScopeType
    tool_calls: list[PlannedToolCall] = Field(default_factory=list)
    reason: str = ""
    direct_response: str = ""
    use_answerer: bool = False


def generate_execution_plan(
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
    validation_error: str | None = None,
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
    if validation_error:
        messages.append(
            AgentChatMessage(
                role="user",
                content=(
                    "上一轮计划没有通过本地校验，请修正后重新输出。\n"
                    f"校验错误：{validation_error}"
                ),
            )
        )
    try:
        payload = gateway.create_structured_completion(messages, PlannerOutput)
        return _convert_planner_output(payload)
    except NotImplementedError:
        raw_output = gateway.create_text_completion(messages).strip()
        return _parse_execution_plan(raw_output)


def _dump_tool_state(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _parse_execution_plan(raw_output: str) -> AgentActionPlan:
    payload = json.loads(raw_output)
    normalized = _normalize_plan_payload(payload)
    return AgentActionPlan.model_validate(normalized)


def _convert_planner_output(payload: PlannerOutput) -> AgentActionPlan:
    return AgentActionPlan.model_validate(
        {
            "scope_type": payload.scope_type,
            "reason": payload.reason,
            "direct_response": payload.direct_response,
            "use_answerer": payload.use_answerer,
            "tool_calls": [
                _planned_tool_call_to_payload(item)
                for item in payload.tool_calls
            ],
        }
    )


def _normalize_plan_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("planner 必须返回 JSON object。")
    normalized = dict(payload)
    raw_tool_calls = normalized.get("tool_calls", [])
    if isinstance(raw_tool_calls, list):
        normalized["tool_calls"] = [_normalize_tool_call(item) for item in raw_tool_calls]
    return normalized


def _normalize_tool_call(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("tool_call 必须是 JSON object。")
    if "tool_name" in value:
        return dict(value)
    name = value.get("name")
    arguments = value.get("arguments", {})
    if not isinstance(name, str) or not name.strip():
        raise ValueError("tool_call 缺少 name/tool_name。")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValueError("tool_call.arguments 必须是 object。")
    return {
        "tool_name": name.strip(),
        **arguments,
    }


def _planned_tool_call_to_payload(item: PlannedToolCall) -> dict[str, object]:
    payload: dict[str, object] = {
        "tool_name": item.name.value,
    }
    if item.series_id is not None:
        payload["series_id"] = item.series_id
    if item.video_id is not None:
        payload["video_id"] = item.video_id
    if item.video_ids:
        payload["video_ids"] = item.video_ids
    if item.seek_seconds is not None:
        payload["seek_seconds"] = item.seek_seconds
    if item.match_end_seconds is not None:
        payload["match_end_seconds"] = item.match_end_seconds
    if item.matched_text:
        payload["matched_text"] = item.matched_text
    if item.chapter_title:
        payload["chapter_title"] = item.chapter_title
    if item.query:
        payload["query"] = item.query
    if item.note_title:
        payload["note_title"] = item.note_title
    if item.note_content:
        payload["note_content"] = item.note_content
    return payload
