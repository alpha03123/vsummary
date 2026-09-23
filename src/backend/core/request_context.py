"""Request-scoped ownership context available to infrastructure adapters."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

from backend.core.context import WorkspaceContext


_workspace_context: ContextVar[WorkspaceContext | None] = ContextVar("workspace_context", default=None)


def get_workspace_context() -> WorkspaceContext | None:
    return _workspace_context.get()


@contextmanager
def bind_workspace_context(context: WorkspaceContext) -> Iterator[None]:
    token: Token[WorkspaceContext | None] = _workspace_context.set(context)
    try:
        yield
    finally:
        _workspace_context.reset(token)
