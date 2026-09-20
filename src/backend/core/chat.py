"""Product-neutral chat message contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.core.citations import CitationReference


MessageRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    citations: list[CitationReference] = Field(default_factory=list)
