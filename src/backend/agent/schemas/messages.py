from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


MessageRole = Literal["system", "user", "assistant"]


class AgentChatMessage(BaseModel):
    role: MessageRole
    content: str
