"""Product-neutral quota and usage contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.core.context import WorkspaceContext


@dataclass(frozen=True)
class UsageEstimate:
    units: int = 0
    storage_bytes: int = 0
    operation_id: str = ""
    operation: str = ""
    model_profile: str | None = None
    duration_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    transcript_available: bool | None = None
    multimodal_enabled: bool = False
    children: tuple[UsageEstimate, ...] = ()
    artifacts: tuple[UsageEstimate, ...] = ()


@dataclass(frozen=True)
class UsageRecord:
    units: int = 0
    storage_bytes: int = 0
    operation_id: str = ""
    operation: str = ""
    model_profile: str | None = None
    duration_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    transcript_available: bool | None = None
    multimodal_enabled: bool = False
    children: tuple[UsageRecord, ...] = ()
    artifacts: tuple[UsageRecord, ...] = ()

    @classmethod
    def from_dict(cls, data):
        values = dict(data)
        for field in ("children", "artifacts"):
            values[field] = tuple(cls.from_dict(item) for item in data.get(field, ()))
        return cls(**values)


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


class UnlimitedQuotaGuard:
    """Explicit unlimited policy for hosts that do not impose billing quotas."""

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
        return QuotaReservation(id=f"unlimited:{idempotency_key}")

    def settle(self, reservation_id: str, actual: UsageRecord) -> None:
        del reservation_id, actual

    def release(self, reservation_id: str, reason: str) -> None:
        del reservation_id, reason


class NoopUsageMeter:
    """Explicit host policy that does not record additional quota units."""

    def record(self, context: WorkspaceContext, usage: UsageRecord) -> None:
        del context, usage
