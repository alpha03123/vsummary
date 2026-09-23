"""Composition primitives exclusive to the single-user Local product."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.core.context import WorkspaceContext
from backend.core.capabilities import CapabilitySet

if TYPE_CHECKING:
    from backend.api.di.workspace_services import WorkspaceServices


@dataclass(frozen=True)
class LocalWorkspaceContextProvider:
    """Provides the installation's one explicit workspace without Core fallback."""

    workspace_id: str
    actor_id: str = "local-user"

    def __post_init__(self) -> None:
        if not self.workspace_id.strip():
            raise ValueError("Local workspace_id is required.")

    def get_context(self, *, request_id: str) -> WorkspaceContext:
        return WorkspaceContext(
            workspace_id=self.workspace_id,
            actor_id=self.actor_id,
            request_id=request_id,
        )


@dataclass
class LocalWorkspaceServicesProvider:
    """Owns Local's explicitly constructed single-workspace service scope."""

    workspace_id: str
    _services: WorkspaceServices | None = None

    def __post_init__(self) -> None:
        if not self.workspace_id.strip():
            raise ValueError("Local workspace_id is required.")

    def get_services(self, context: WorkspaceContext) -> WorkspaceServices:
        if context.workspace_id != self.workspace_id:
            raise LookupError(f"workspace not available in this Local installation: {context.workspace_id}")
        if self._services is None:
            raise RuntimeError("Local workspace services have not been composed.")
        return self._services

    def install_services(self, services: WorkspaceServices) -> None:
        if services.workspace_id != self.workspace_id:
            raise ValueError("Local workspace services must match the installation workspace.")
        self._services = services


def build_local_container(root_dir: Path, *, workspace: Any):
    """Compose Core services with the Local-only identity and policy adapters."""

    from backend.api.di.bootstrap import build_api_container
    from backend.core.quota import LocalUnlimitedQuotaGuard, LocalUsageMeter

    services_provider = LocalWorkspaceServicesProvider(workspace_id=workspace.workspace_id)
    container, services = build_api_container(
        root_dir,
        workspace_override=workspace,
        context_provider=LocalWorkspaceContextProvider(workspace_id=workspace.workspace_id),
        workspace_services_provider=services_provider,
        quota_guard=LocalUnlimitedQuotaGuard(),
        usage_meter=LocalUsageMeter(),
        capabilities=CapabilitySet(local_file_picker=True, model_download=True),
    )
    services_provider.install_services(services)
    return container
