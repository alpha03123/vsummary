"""Explicit workspace scopes for HTTP test containers."""

from __future__ import annotations

from backend.local.composition import LocalWorkspaceContextProvider, LocalWorkspaceServicesProvider


def attach_workspace_scope(container: object, *, workspace_id: str = "workspace-1") -> object:
    """Make a fake HTTP container obey the production workspace-scope contract."""

    container.workspace_id = workspace_id
    container.context_provider = LocalWorkspaceContextProvider(workspace_id=workspace_id, actor_id="test-user")
    container.workspace_services_provider = LocalWorkspaceServicesProvider(workspace_id=workspace_id)
    container.workspace_services_provider.install_services(container)
    return container
