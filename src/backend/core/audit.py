"""Audit event contract for product-specific audit implementations."""

from __future__ import annotations

from typing import Protocol

from backend.core.context import WorkspaceContext


class AuditSink(Protocol):
    def record(self, context: WorkspaceContext, action: str, details: dict[str, object]) -> None: ...
