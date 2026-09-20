"""Purpose-bound secret lookup contract."""

from __future__ import annotations

from typing import Protocol

from backend.core.context import WorkspaceContext


class SecretProvider(Protocol):
    def get_secret(self, context: WorkspaceContext, purpose: str) -> str | None: ...
