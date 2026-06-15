"""video scope 下的动作规划器（LLM 决策 → 结构化计划）。

本模块负责在 LangGraph 的 `plan_and_execute_video_actions` 节点中调用 LLM，
让模型基于用户问题、检索证据、记忆上下文与可用工具 schema，决定本次
video scope 应该执行哪些工具调用；规划结果会被 `ActionDispatcher` 进一步
分发执行。
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from backend.agent.schemas.messages import AgentChatMessage
from backend.agent.schemas.tool_calls import (
    OpenNotesCall,
    SaveNoteCall,
    ToolCall,
    ToolName,
    VideoSeekCall,
)
from backend.agent_graph.prompts import VIDEO_ACTION_PLANNER_SYSTEM_PROMPT


class PlannedVideoToolCall(BaseModel):
    """LLM 输出的单条 video scope 工具调用（待校验的中间形态）。

    Attributes:
        tool_name: 目标工具名，仅允许 `open_notes` / `save_note` / `video_seek`。
        note_title: `save_note` 时的笔记标题。
        note_content: `save_note` 时的笔记正文。
        seek_seconds: `video_seek` 时的跳转秒数。
        match_end_seconds: `video_seek` 时命中文本的结束秒数。
        matched_text: `video_seek` 时匹配到的文本片段。
        chapter_title: `video_seek` 时命中的章节标题。
        query: `video_seek` 时附带的检索 query。
    """

    tool_name: Literal["open_notes", "save_note", "video_seek"]
    note_title: str = ""
    note_content: str = ""
    seek_seconds: float | None = None
    match_end_seconds: float | None = None
    matched_text: str = ""
    chapter_title: str = ""
    query: str = ""

    @model_validator(mode="after")
    def validate_arguments_for_tool(self) -> PlannedVideoToolCall:
        """按工具名校验必填参数；缺失时抛出 `ValueError`。"""
        if self.tool_name == "save_note" and (
            not self.note_title.strip() or not self.note_content.strip()
        ):
            raise ValueError("save_note 需要 note_title 和 note_content。")
        if self.tool_name == "video_seek" and self.seek_seconds is None:
            raise ValueError("video_seek 需要 seek_seconds。")
        return self


class VideoActionPlannerPayload(BaseModel):
    """LLM 结构化输出：`VideoActionPlanner` 的一次完整规划结果。

    Attributes:
        tool_calls: 模型决定执行的多条工具调用（最多 2 条，会在下游裁剪）。
        action_summary: 对本次规划的简短文字说明（供回答引用）。
    """

    tool_calls: list[PlannedVideoToolCall] = Field(default_factory=list)
    action_summary: str = ""


class VideoActionPlan(BaseModel):
    """经过校验与裁剪后的最终 video scope 动作计划。

    Attributes:
        tool_calls: 校验通过的工具调用列表（最多 2 条）。
        action_summary: 规划的文字说明，已 `strip`。
    """

    tool_calls: list[ToolCall] = Field(default_factory=list)
    action_summary: str = ""


VIDEO_ACTION_TOOL_MODELS = {
    ToolName.OPEN_NOTES: OpenNotesCall,
    ToolName.SAVE_NOTE: SaveNoteCall,
    ToolName.VIDEO_SEEK: VideoSeekCall,
}
ALLOWED_VIDEO_ACTIONS = frozenset(VIDEO_ACTION_TOOL_MODELS)
_TOOL_CALL_ADAPTER = TypeAdapter(ToolCall)


class VideoActionPlanner:
    """video scope 下的动作规划器：把 LLM 决策包装为 `VideoActionPlan`。

    业务目的：在 LangGraph 的 video scope 链路上，调用 LLM 让模型基于
    上下文决定要打开/记录/跳转哪些工具，再由 dispatcher 真正执行。

    关键不变量：
        - 只暴露 `open_notes` / `save_note` / `video_seek` 三类工具，
          通过 `ALLOWED_VIDEO_ACTIONS` 白名单约束；
        - 一次规划最多保留 2 条工具调用，避免一次回合操作过多；
        - 可选 `debug_trace` 入参会把"输入 + LLM 输出"完整落盘，便于排障。
    """

    def __init__(self, *, gateway) -> None:
        """注入 LLM 结构化输出网关（实现 `ChatGateway.create_structured_completion`）。"""
        self._gateway = gateway

    def run(
        self,
        *,
        user_message: str,
        retrieval_results: list[dict[str, object]],
        memory_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> VideoActionPlan:
        """基于用户消息、检索证据与记忆上下文，调用 LLM 产出本次 video 动作计划。

        Args:
            user_message: 用户原始提问文本。
            retrieval_results: 已收集到的检索证据列表（节点上下文中的 `evidence_items`
                或 `retrieval_results`）。
            memory_messages: 可选的会话记忆消息列表（按 `{role, content}` 字典传入）。
            debug_trace: 可选的调试追踪字典；非 `None` 时会把输入/输出完整写入。

        Returns:
            校验并裁剪后的 `VideoActionPlan`，最多包含 2 条工具调用。
        """
        messages = _build_messages(
            user_message=user_message,
            retrieval_results=retrieval_results,
            memory_messages=memory_messages or [],
        )
        payload = self._gateway.create_structured_completion(
            messages,
            response_model=VideoActionPlannerPayload,
        )
        plan = _coerce_plan(payload)
        if debug_trace is not None:
            debug_trace["video_action_planner"] = {
                "input": {
                    "user_message": user_message,
                    "tool_schemas": _build_tool_schema_specs(),
                    "retrieval_results": _render_evidence(retrieval_results),
                },
                "output": {
                    "tool_calls": [call.model_dump(mode="json") for call in plan.tool_calls],
                    "action_summary": plan.action_summary,
                },
            }
        return plan


def _coerce_plan(payload: VideoActionPlannerPayload) -> VideoActionPlan:
    """把 LLM 输出的 payload 转换为合规的 `VideoActionPlan`。

    流程：按工具名构造最小 payload → 用 `TypeAdapter` 校验 → 白名单校验 →
    截断到最多 2 条调用。

    Raises:
        ValueError: LLM 输出的工具名不在 `ALLOWED_VIDEO_ACTIONS` 白名单内。
    """
    calls: list[ToolCall] = []
    for item in payload.tool_calls:
        call_payload = _build_tool_call_payload(item)
        call = _TOOL_CALL_ADAPTER.validate_python(call_payload)
        if call.tool_name not in ALLOWED_VIDEO_ACTIONS:
            raise ValueError(f"video action 不允许工具: {call.tool_name.value}")
        calls.append(call)
    return VideoActionPlan(
        tool_calls=calls[:2],
        action_summary=payload.action_summary.strip(),
    )


def _build_tool_call_payload(item: PlannedVideoToolCall) -> dict[str, object]:
    """根据工具名将 `PlannedVideoToolCall` 投影为 `ToolCall` 校验所需的最小字典。

    不同工具需要的字段不同：`open_notes` 只需名称；`save_note` 需要标题与正文；
    其他（即 `video_seek`）携带跳转相关字段。
    """
    if item.tool_name == "open_notes":
        return {"tool_name": item.tool_name}
    if item.tool_name == "save_note":
        return {
            "tool_name": item.tool_name,
            "note_title": item.note_title.strip(),
            "note_content": item.note_content.strip(),
        }
    return {
        "tool_name": item.tool_name,
        "seek_seconds": item.seek_seconds,
        "match_end_seconds": item.match_end_seconds,
        "matched_text": item.matched_text,
        "chapter_title": item.chapter_title,
        "query": item.query,
    }


def _build_messages(
    *,
    user_message: str,
    retrieval_results: list[dict[str, object]],
    memory_messages: list[dict[str, object]],
) -> list[AgentChatMessage]:
    """构造送往 LLM 的 system + user 双轮消息。

    Args:
        user_message: 用户原始提问。
        retrieval_results: 检索证据列表（会经过 `_render_evidence` 截断）。
        memory_messages: 会话记忆消息列表。

    Returns:
        包含 1 条 system 提示词与 1 条 JSON 化 user 上下文的 `AgentChatMessage` 列表。
    """
    return [
        AgentChatMessage(
            role="system",
            content=VIDEO_ACTION_PLANNER_SYSTEM_PROMPT,
        ),
        AgentChatMessage(
            role="user",
            content=(
                f"user_message:\n{user_message}\n\n"
                f"memory_messages:\n{json.dumps(memory_messages, ensure_ascii=False, indent=2)}\n\n"
                f"allowed_tool_schemas:\n{json.dumps(_build_tool_schema_specs(), ensure_ascii=False, indent=2)}\n\n"
                f"evidence:\n{json.dumps(_render_evidence(retrieval_results), ensure_ascii=False, indent=2)}"
            ),
        ),
    ]


def _build_tool_schema_specs() -> list[dict[str, object]]:
    """生成 LLM 可消费的工具 schema 列表（`{tool_name, schema}` 字典数组）。"""
    return [
        {
            "tool_name": tool_name.value,
            "schema": model.model_json_schema(),
        }
        for tool_name, model in VIDEO_ACTION_TOOL_MODELS.items()
    ]


def _render_evidence(retrieval_results: list[dict[str, object]]) -> list[dict[str, object]]:
    """把检索证据投影为 LLM 友好的精简字典列表（`text` 截断到 2000 字）。

    Args:
        retrieval_results: 原始检索 hit 字典列表，非字典项会被静默跳过。

    Returns:
        含 `index` / `source_type` / `title` / 时间戳 / 截断后 `text` 等字段的字典列表。
    """
    rendered: list[dict[str, object]] = []
    for index, item in enumerate(retrieval_results, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("snippet") or item.get("text") or "").strip()
        rendered.append(
            {
                "index": index,
                "source_type": str(item.get("source_type", "")).strip(),
                "source_family": str(item.get("source_family", "")).strip(),
                "title": str(item.get("title", "")).strip(),
                "start_seconds": item.get("start_seconds"),
                "end_seconds": item.get("end_seconds"),
                "chapter_title": item.get("chapter_title"),
                "text": text[:2000],
            }
        )
    return rendered
