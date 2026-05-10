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
        if self.tool_name == "save_note" and (
            not self.note_title.strip() or not self.note_content.strip()
        ):
            raise ValueError("save_note 需要 note_title 和 note_content。")
        if self.tool_name == "video_seek" and self.seek_seconds is None:
            raise ValueError("video_seek 需要 seek_seconds。")
        return self


class VideoActionPlannerPayload(BaseModel):
    tool_calls: list[PlannedVideoToolCall] = Field(default_factory=list)
    action_summary: str = ""


class VideoActionPlan(BaseModel):
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
    def __init__(self, *, gateway) -> None:
        self._gateway = gateway

    def run(
        self,
        *,
        user_message: str,
        retrieval_results: list[dict[str, object]],
        memory_messages: list[dict[str, object]] | None = None,
        debug_trace: dict[str, object] | None = None,
    ) -> VideoActionPlan:
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
    return [
        {
            "tool_name": tool_name.value,
            "schema": model.model_json_schema(),
        }
        for tool_name, model in VIDEO_ACTION_TOOL_MODELS.items()
    ]


def _render_evidence(retrieval_results: list[dict[str, object]]) -> list[dict[str, object]]:
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
