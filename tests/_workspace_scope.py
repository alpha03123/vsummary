"""Explicit workspace scopes for HTTP test containers."""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.context import WorkspaceContext


def attach_workspace_scope(container: object, *, workspace_id: str = "workspace-1") -> object:
    """Make a fake HTTP container obey the production workspace-scope contract."""

    def get_context(*, request_id: str) -> WorkspaceContext:
        return WorkspaceContext(workspace_id=workspace_id, actor_id="test-user", request_id=request_id)

    def get_services(context: WorkspaceContext) -> object:
        if context.workspace_id != workspace_id:
            raise LookupError("workspace missing")
        return container

    container.workspace_id = workspace_id
    container.context_provider = SimpleNamespace(get_context=get_context)
    container.workspace_services_provider = SimpleNamespace(get_services=get_services)
    return container
