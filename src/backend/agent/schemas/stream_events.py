from __future__ import annotations

from pydantic import BaseModel, Field


class AgentStreamEvent(BaseModel):
    type: str
    payload: dict[str, object] = Field(default_factory=dict)
