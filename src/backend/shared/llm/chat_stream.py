from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChatCompletionStreamChunk:
    delta: str = ""
    usage: dict[str, int] = field(default_factory=dict)
