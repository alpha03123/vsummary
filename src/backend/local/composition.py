"""Composition primitives exclusive to the single-user Local product."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.context import WorkspaceContext
from backend.core.capabilities import CapabilitySet


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


def build_local_container(root_dir: Path, *, workspace: Any):
    """Compose Core services with the Local-only identity and policy adapters."""

    from backend.api.di.bootstrap import build_api_container
    from backend.core.quota import LocalUnlimitedQuotaGuard, LocalUsageMeter

    return build_api_container(
        root_dir,
        workspace_override=workspace,
        context_provider=LocalWorkspaceContextProvider(workspace_id=workspace.workspace_id),
        quota_guard=LocalUnlimitedQuotaGuard(),
        usage_meter=LocalUsageMeter(),
        capabilities=CapabilitySet(local_file_picker=True, model_download=True),
    )
