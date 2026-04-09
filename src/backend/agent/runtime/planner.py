from __future__ import annotations

import json
from pydantic import BaseModel, Field

from backend.agent.memory.context import AgentContext
from backend.agent.ports import ChatGateway
from backend.agent.runtime.note_drafter import draft_video_note
from backend.agent.schemas.action_plan import AgentActionPlan, ScopeType
from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import ToolExecutionResult, ToolName, ToolPlane
from backend.agent.tools import list_model_visible_tool_definitions_for_context

PLANNER_TRANSPORT_STRUCTURED = "structured"
PLANNER_TRANSPORT_STREAM_BUFFERED = "stream_buffered"


INITIAL_PLANNER_SYSTEM_PROMPT = (
    "你是视频知识工作台中的执行计划器。\n"
    "你的任务不是给问题贴标签，而是直接决定下一步该不该调用工具、调用哪些工具，或者是否已经可以直接回复。\n"
    "规则：\n"
    "1. 只能使用输入中提供的工具列表，绝对不要发明工具名。\n"
    "2. 如果还需要读取信息或执行动作，就填写 tool_calls。\n"
    "3. 如果已经拿到足够证据，应该交给回答器来组织自然回答，就设置 use_answerer=true，tool_calls 留空，direct_response 留空。\n"
    "4. 如果当前不需要工具也不需要回答器，例如问候、超范围拒绝、动作完成后的自然收口，请直接填写 direct_response。\n"
    "5. 如果用户请求明显超出当前视频知识工作台范围，direct_response 应礼貌说明边界，并引导回到当前工作台支持的任务；不要继续承诺完成无关任务。\n"
    "6. direct_response 必须是自然中文回复，不要暴露 tool_name、payload、schema、规划这些内部实现词。\n"
    "7. tool_calls、direct_response、use_answerer 三者只能激活一种：\n"
    "   - 要继续工作：tool_calls 非空\n"
    "   - 要直接回复：direct_response 非空\n"
    "   - 要基于现有证据回答：use_answerer=true\n"
    "8. 如果用户请求混合多个动作，可以在同一轮输出多个 tool_calls。\n"
    "9. 在 series 上下文里，get_video_summary / get_video_transcript / get_video_tools 这类深层读取工具必须带明确 video_id；如果当前还无法确定 video_id，就不要调用这些工具，而是先 list_series_videos，或者直接用 direct_response 说明需要用户进一步明确。\n"
    "10. open_* / generate_* / save_note 这类动作工具，只有当用户明确要求打开、生成、记录时才调用；普通问答不要调用页面切换工具。\n"
    "11. 只输出 JSON，不要输出代码块，不要解释。\n"
    '12. JSON 格式固定为 {"scope_type":"series或video","tool_calls":[...],"reason":"...","direct_response":"...","use_answerer":true或false}。\n'
    "13. 输入中如果包含 validation_error 或 previous_plan，说明上一轮计划未通过本地校验；你必须基于错误提示修正，并优先保持 previous_plan 的整体意图不变，只修正不合法的字段或工具选择。\n"
    "14. series 上下文里，所有需要 video_id 的读取工具都必须使用最近一次 list_series_videos 返回的真实 video_id。\n"
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
    previous_plan: AgentActionPlan | None = None,
    direct_response_only: bool = False,
    planner_transport: str = PLANNER_TRANSPORT_STRUCTURED,
) -> AgentActionPlan:
    system_prompt = DIRECT_RESPONSE_ONLY_SYSTEM_PROMPT if direct_response_only else INITIAL_PLANNER_SYSTEM_PROMPT
    messages = [
        AgentChatMessage(role="system", content=system_prompt),
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
                        "inspection_stage": context.inspection_stage.value,
                        "chapter_titles": list(context.chapter_titles),
                        "overview": _dump_tool_state(context.overview),
                        "mindmap": _dump_tool_state(context.mindmap),
                        "knowledge_cards": _dump_tool_state(context.knowledge_cards),
                        "notes": _dump_tool_state(context.notes),
                        "preview": _dump_tool_state(context.preview),
                        "recent_messages": context.recent_messages,
                    },
                    "available_tools": _build_planner_visible_tools(context),
                    "observed_tool_results": [
                        {
                            "tool_name": result.tool_name.value,
                            "status": result.status,
                            "payload": result.payload,
                        }
                        for result in observed_tool_results
                    ],
                    "validation_error": validation_error,
                    "previous_plan": previous_plan.model_dump(mode="json") if previous_plan else None,
                },
                ensure_ascii=False,
                indent=2,
            ),
        ),
    ]
    if planner_transport == PLANNER_TRANSPORT_STREAM_BUFFERED:
        raw_output = _collect_streamed_planner_output(gateway, messages)
        return _parse_execution_plan(
            raw_output,
            gateway=gateway,
            context=context,
            user_message=user_message,
            observed_tool_results=observed_tool_results,
        )
    try:
        payload = gateway.create_structured_completion(messages, PlannerOutput)
        return _convert_planner_output(
            payload,
            gateway=gateway,
            context=context,
            user_message=user_message,
            observed_tool_results=observed_tool_results,
        )
    except NotImplementedError:
        raw_output = gateway.create_text_completion(messages).strip()
        return _parse_execution_plan(
            raw_output,
            gateway=gateway,
            context=context,
            user_message=user_message,
            observed_tool_results=observed_tool_results,
        )


DIRECT_RESPONSE_ONLY_SYSTEM_PROMPT = (
    "你是视频知识工作台中的执行计划器。\n"
    "当前要求你不要再调用任何工具，只输出一条自然中文 direct_response。\n"
    "规则：\n"
    "1. tool_calls 必须为空。\n"
    "2. use_answerer 必须为 false。\n"
    "3. 如果用户请求明显超出当前视频知识工作台范围，要礼貌说明边界，并引导回到当前工作台支持的任务；不要继续承诺完成无关任务。\n"
    "4. 如果只是信息不足，就礼貌说明限制并要求用户补充必要信息。\n"
    "5. 不要暴露 tool_name、payload、schema、规划、校验失败这些内部实现词。\n"
    '6. JSON 格式固定为 {"scope_type":"series或video","tool_calls":[],"reason":"...","direct_response":"...","use_answerer":false}。\n'
)


def _dump_tool_state(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _collect_streamed_planner_output(
    gateway: ChatGateway,
    messages: list[AgentChatMessage],
) -> str:
    chunks = list(gateway.create_text_completion_stream(messages))
    raw_output = "".join(chunks).strip()
    if raw_output:
        return raw_output
    return gateway.create_text_completion(messages).strip()


def _parse_execution_plan(
    raw_output: str,
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
) -> AgentActionPlan:
    payload = json.loads(raw_output)
    normalized = _normalize_plan_payload(payload)
    return _convert_plan_payload(
        normalized,
        gateway=gateway,
        context=context,
        user_message=user_message,
        observed_tool_results=observed_tool_results,
    )


def _convert_planner_output(
    payload: PlannerOutput,
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
) -> AgentActionPlan:
    return _convert_plan_payload(
        {
            "scope_type": payload.scope_type,
            "reason": payload.reason,
            "direct_response": payload.direct_response,
            "use_answerer": payload.use_answerer,
            "tool_calls": [
                _planned_tool_call_to_payload(item)
                for item in payload.tool_calls
            ],
        },
        gateway=gateway,
        context=context,
        user_message=user_message,
        observed_tool_results=observed_tool_results,
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


def _convert_plan_payload(
    payload: dict[str, object],
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
) -> AgentActionPlan:
    repaired = _repair_plan_payload(
        payload,
        gateway=gateway,
        context=context,
        user_message=user_message,
        observed_tool_results=observed_tool_results,
    )
    return AgentActionPlan.model_validate(repaired)


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


def _repair_plan_payload(
    payload: dict[str, object],
    *,
    gateway: ChatGateway,
    context: AgentContext,
    user_message: str,
    observed_tool_results: list[ToolExecutionResult],
) -> dict[str, object]:
    repaired = dict(payload)
    raw_tool_calls = repaired.get("tool_calls", [])
    if not isinstance(raw_tool_calls, list):
        return repaired

    evidence_result = _extract_latest_note_evidence(observed_tool_results)
    next_tool_calls: list[dict[str, object]] = []
    inserted_evidence_read = False

    for item in raw_tool_calls:
        if not isinstance(item, dict):
            next_tool_calls.append(item)
            continue
        if str(item.get("tool_name", "")).strip() != ToolName.SAVE_NOTE.value:
            next_tool_calls.append(item)
            continue
        title = str(item.get("note_title", "")).strip()
        content = str(item.get("note_content", "")).strip()
        if title and content:
            next_tool_calls.append(item)
            continue
        if evidence_result is not None:
            draft = draft_video_note(
                gateway=gateway,
                user_message=user_message,
                evidence_result=evidence_result,
            )
            next_tool_calls.append(
                {
                    **item,
                    "note_title": draft.note_title,
                    "note_content": draft.note_content,
                }
            )
            continue
        if (
            not inserted_evidence_read
            and context.scope_type == "video"
            and context.series_id
            and context.video_id
        ):
            next_tool_calls.append(
                {
                    "tool_name": ToolName.GET_VIDEO_SUMMARY.value,
                    "series_id": context.series_id,
                    "video_id": context.video_id,
                }
            )
            inserted_evidence_read = True
        repaired["direct_response"] = ""
        repaired["use_answerer"] = False

    repaired["tool_calls"] = next_tool_calls
    return repaired


def _extract_latest_note_evidence(
    observed_tool_results: list[ToolExecutionResult],
) -> ToolExecutionResult | None:
    for result in reversed(observed_tool_results):
        if result.tool_name == ToolName.GET_VIDEO_SUMMARY and result.status == "ok":
            return result
        if result.tool_name == ToolName.GET_VIDEO_TRANSCRIPT and result.status == "ok":
            return result
    return None


def _build_planner_visible_tools(context: AgentContext) -> list[dict[str, object]]:
    tools = list_model_visible_tool_definitions_for_context(context)
    tools.sort(
        key=lambda tool: (
            0 if tool.plane == ToolPlane.BUSINESS_READ else 1,
            tool.name.value,
        )
    )
    return [
        {
            # 保留 name 字段以兼容旧版 gateway stub。
            "name": tool.name.value,
            "title": tool.title,
            "description": tool.description,
            "arguments": tool.arguments,
            "plane": tool.plane.value,
            "batch_tag": tool.batch_tag,
            "requires_video_id": tool.requires_video_id,
            "contexts": [tag.value for tag in tool.contexts],
            "intents": [tag.value for tag in tool.intents],
        }
        for tool in tools
    ]
