from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.agent.schemas.action_plan import CitationReference


MessageRole = Literal["system", "user", "assistant"]


class AgentChatMessage(BaseModel):
    role: MessageRole
    content: str
    citations: list[CitationReference] = Field(default_factory=list)
