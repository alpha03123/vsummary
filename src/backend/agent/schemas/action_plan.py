from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult, ToolName
from backend.agent.tools import BUSINESS_READ_TOOL_DEFINITIONS, UI_ACTION_TOOL_DEFINITIONS


class IntentType(str, Enum):
    ANSWER_QUESTION = "answer_question"
    SERIES_LOCATE = "series_locate"
    OPEN_TOOL = "open_tool"
    SEEK_VIDEO = "seek_video"
    SAVE_NOTE = "save_note"
    GENERATE_OVERVIEW = "generate_overview"
    GENERATE_MINDMAP = "generate_mindmap"
    SERIES_ANSWER = "series_answer"
    OUT_OF_SCOPE = "out_of_scope"


class ScopeType(str, Enum):
    SERIES = "series"
    VIDEO = "video"


PlannerToolName = Enum(
    "PlannerToolName",
    {
        tool.name.name: tool.name.value
        for tool in [
            *BUSINESS_READ_TOOL_DEFINITIONS,
            *UI_ACTION_TOOL_DEFINITIONS,
        ]
    },
    type=str,
)


class PlannerToolCall(BaseModel):
    tool_name: PlannerToolName
    series_id: str | None = None
    video_id: str | None = None
    video_ids: list[str] = Field(default_factory=list)
    seek_seconds: float | None = None
    note_title: str | None = None
    note_content: str | None = None
    query: str | None = None
    reason: str = ""


class AgentActionPlan(BaseModel):
    intent_type: IntentType
    scope_type: ScopeType
    assistant_message: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reason: str = ""
    out_of_scope_reason: str = ""


class AgentTurnResult(BaseModel):
    assistant_message: str
    plan: AgentActionPlan
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
