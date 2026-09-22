"""Request-scoped ownership context required by Core use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar


@dataclass(frozen=True)
class WorkspaceContext:
    """The authenticated actor and workspace that own an operation."""

    workspace_id: str
    actor_id: str
    request_id: str

    def __post_init__(self) -> None:
        if not self.workspace_id.strip():
            raise ValueError("workspace_id is required.")
        if not self.actor_id.strip():
            raise ValueError("actor_id is required.")
        if not self.request_id.strip():
            raise ValueError("request_id is required.")


class WorkspaceContextProvider(Protocol):
    """Resolves a complete context at an application boundary."""

    def get_context(self, *, request_id: str) -> WorkspaceContext: ...


WorkspaceServicesT = TypeVar("WorkspaceServicesT", covariant=True)


class WorkspaceServicesProvider(Protocol[WorkspaceServicesT]):
    """Resolves the application services owned by one WorkspaceContext.

    Core owns this selection contract. Local and Cloud own the concrete service
    lifetime, caching, and storage topology behind it.
    """

    def get_services(self, context: WorkspaceContext) -> WorkspaceServicesT: ...
