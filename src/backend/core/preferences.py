"""User preference storage contract."""

from __future__ import annotations

from typing import Protocol

from backend.core.context import WorkspaceContext


class UserPreferenceStore(Protocol):
    def get(self, context: WorkspaceContext) -> dict[str, object]: ...

    def update(self, context: WorkspaceContext, values: dict[str, object]) -> dict[str, object]: ...
