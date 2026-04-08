from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.agent.schemas.tool_calls import ToolCall, ToolExecutionResult


class ScopeType(str, Enum):
    SERIES = "series"
    VIDEO = "video"


class AgentActionPlan(BaseModel):
    scope_type: ScopeType
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reason: str = ""
    direct_response: str = ""
    use_answerer: bool = False


class AgentTurnResult(BaseModel):
    assistant_message: str
    plan: AgentActionPlan
    tool_results: list[ToolExecutionResult] = Field(default_factory=list)
