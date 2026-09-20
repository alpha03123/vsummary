"""Dependencies required by product-neutral API routes."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Depends, Request

from backend.api.di.container import ApiContainerDep
from backend.core.context import WorkspaceContext


def get_workspace_context(
    request: Request,
    container: ApiContainerDep,
) -> WorkspaceContext:
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    return container.context_provider.get_context(request_id=request_id)


WorkspaceContextDep = Depends(get_workspace_context)
