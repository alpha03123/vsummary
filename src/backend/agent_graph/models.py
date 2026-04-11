from __future__ import annotations

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    task_id: str
    instruction: str
    depends_on: list[str] = Field(default_factory=list)
    kind_hint: str = ""


class DecomposeDecision(BaseModel):
    tasks: list[AgentTask] = Field(default_factory=list)
    reason: str = ""


class SeriesQueryDecision(BaseModel):
    goal: str
    target_source: str
    context_need: str
    reason: str = ""
    action_name: str = ""
    action_args: dict[str, object] = Field(default_factory=dict)


class CompareSplitDecision(BaseModel):
    queries: list[str] = Field(default_factory=list)
    reason: str = ""
