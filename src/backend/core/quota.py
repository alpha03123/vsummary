"""Product-neutral quota and usage contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.core.context import WorkspaceContext


@dataclass(frozen=True)
class UsageEstimate:
    units: int = 0
    storage_bytes: int = 0


@dataclass(frozen=True)
class UsageRecord:
    units: int = 0
    storage_bytes: int = 0


@dataclass(frozen=True)
class QuotaReservation:
    id: str


class QuotaGuard(Protocol):
    def reserve_job(
        self,
        context: WorkspaceContext,
        operation: str,
        estimate: UsageEstimate,
        idempotency_key: str,
    ) -> QuotaReservation: ...

    def settle(self, reservation_id: str, actual: UsageRecord) -> None: ...

    def release(self, reservation_id: str, reason: str) -> None: ...


class UsageMeter(Protocol):
    def record(self, context: WorkspaceContext, usage: UsageRecord) -> None: ...


class LocalUnlimitedQuotaGuard:
    """Explicit unlimited policy for the single-user Local product."""

    def reserve_job(
        self,
        context: WorkspaceContext,
        operation: str,
        estimate: UsageEstimate,
        idempotency_key: str,
    ) -> QuotaReservation:
        del context, operation, estimate
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required.")
        return QuotaReservation(id=f"local:{idempotency_key}")

    def settle(self, reservation_id: str, actual: UsageRecord) -> None:
        del reservation_id, actual

    def release(self, reservation_id: str, reason: str) -> None:
        del reservation_id, reason


class LocalUsageMeter:
    """Local intentionally does not impose metering while retaining the contract."""

    def record(self, context: WorkspaceContext, usage: UsageRecord) -> None:
        del context, usage
