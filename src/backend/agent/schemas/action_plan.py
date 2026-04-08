from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult


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


class AgentActionPlan(BaseModel):
    scope_type: ScopeType
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reason: str = ""
    direct_response: str = ""
    use_answerer: bool = False
    intent_type: IntentType | None = None
    out_of_scope_reason: str = ""


class AgentTurnResult(BaseModel):
    assistant_message: str
    plan: AgentActionPlan
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
