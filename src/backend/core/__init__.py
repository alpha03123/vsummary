"""Public product-neutral contracts shared by Local and Cloud compositions."""

from backend.core.context import WorkspaceContext, WorkspaceContextProvider, WorkspaceServicesProvider
from backend.core.quota import UnlimitedQuotaGuard, NoopUsageMeter, QuotaGuard, UsageMeter

__all__ = [
    "UnlimitedQuotaGuard",
    "NoopUsageMeter",
    "QuotaGuard",
    "UsageMeter",
    "WorkspaceContext",
    "WorkspaceContextProvider",
    "WorkspaceServicesProvider",
]
