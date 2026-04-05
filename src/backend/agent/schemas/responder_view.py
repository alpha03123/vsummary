from __future__ import annotations

from pydantic import BaseModel, Field


class ResponderToolFact(BaseModel):
    tool_name: str
    status: str
    payload: dict[str, object] = Field(default_factory=dict)


class ResponderInputView(BaseModel):
    user_message: str
    answer_goal: str
    tool_facts: list[ResponderToolFact] = Field(default_factory=list)
