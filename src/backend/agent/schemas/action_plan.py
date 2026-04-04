from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult


class IntentType(str, Enum):
    ANSWER_QUESTION = "answer_question"
    OPEN_TOOL = "open_tool"
    SEEK_VIDEO = "seek_video"
    GENERATE_OVERVIEW = "generate_overview"
    GENERATE_MINDMAP = "generate_mindmap"
    SERIES_ANSWER = "series_answer"
    OUT_OF_SCOPE = "out_of_scope"


class ScopeType(str, Enum):
    LIBRARY = "library"
    SERIES = "series"
    VIDEO = "video"


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
