"""Public product-neutral contracts shared by Local and Cloud compositions."""

from backend.core.context import WorkspaceContext, WorkspaceContextProvider, WorkspaceServicesProvider
from backend.core.quota import LocalUnlimitedQuotaGuard, LocalUsageMeter, QuotaGuard, UsageMeter

__all__ = [
    "LocalUnlimitedQuotaGuard",
    "LocalUsageMeter",
    "QuotaGuard",
    "UsageMeter",
    "WorkspaceContext",
    "WorkspaceContextProvider",
    "WorkspaceServicesProvider",
]
