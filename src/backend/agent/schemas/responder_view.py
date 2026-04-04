from __future__ import annotations

from pydantic import BaseModel, Field


class ResponderFact(BaseModel):
    kind: str
    value: str


class ResponderToolFact(BaseModel):
    tool_name: str
    status: str
    facts: list[ResponderFact] = Field(default_factory=list)


class ResponderInputView(BaseModel):
    user_message: str
    answer_goal: str
    tool_facts: list[ResponderToolFact] = Field(default_factory=list)
