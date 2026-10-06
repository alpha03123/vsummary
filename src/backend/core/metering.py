"""Host-injected resource budgets and measured usage, independent of points or currencies."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Protocol, Mapping

from backend.core.context import WorkspaceContext
from backend.core.ids import new_ulid
from backend.core.request_context import get_workspace_context


@dataclass(frozen=True)
class ResourceUsage:
    resource: str
    model: str
    call_id: str = ""
    operation_id: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_seconds: float | None = None
    estimated: bool = False


class ResourceBudget(Protocol):
    def reserve(self, context: WorkspaceContext, estimate: ResourceUsage) -> str: ...
    def settle(self, reservation_id: str, actual: ResourceUsage) -> None: ...


_budget: ContextVar[ResourceBudget | None] = ContextVar("resource_budget", default=None)
_operation: ContextVar[str | None] = ContextVar("usage_operation_id", default=None)


def current_operation_id() -> str | None:
    return _operation.get()


@contextmanager
def bind_resource_budget(budget: ResourceBudget | None, operation_id: str | None = None):
    budget_token = _budget.set(budget)
    operation_token = _operation.set(operation_id)
    try:
        yield
    finally:
        _operation.reset(operation_token)
        _budget.reset(budget_token)


def resource_budget_enabled() -> bool:
    return _budget.get() is not None


def response_usage(response, *, require_output=False) -> tuple[int, int]:
    value = response.get("usage") if isinstance(response, Mapping) else getattr(response, "usage", None)
    if value is None:
        raise ValueError("Provider response is missing billable usage.")
    if not isinstance(value, Mapping):
        value = value.model_dump() if hasattr(value, "model_dump") else vars(value)
    incoming = value.get("prompt_tokens", value.get("input_tokens", value.get("total_tokens") if not require_output else None))
    outgoing = value.get("completion_tokens", value.get("output_tokens", None if require_output else 0))
    if type(incoming) is not int or type(outgoing) is not int or incoming < 0 or outgoing < 0:
        raise ValueError("Provider response contains invalid billable usage.")
    return incoming, outgoing


class ResourceCall:
    def __init__(self, estimate):
        self.budget = _budget.get()
        self.estimate = replace(estimate, call_id=new_ulid(), operation_id=current_operation_id() or "", estimated=True)
        self.reservation = None
        self.completed = False

    def complete(self, *, input_tokens=None, output_tokens=None, duration_seconds=None):
        if self.budget is not None:
            actual = replace(self.estimate, input_tokens=input_tokens, output_tokens=output_tokens, duration_seconds=duration_seconds, estimated=False)
            self.budget.settle(self.reservation, actual)
        self.completed = True


@contextmanager
def resource_call(estimate: ResourceUsage):
    call = ResourceCall(estimate)
    if call.budget is not None:
        context = get_workspace_context()
        if context is None:
            raise RuntimeError("Resource budgeting requires workspace ownership.")
        call.reservation = call.budget.reserve(context, call.estimate)
    try:
        yield call
    finally:
        if call.budget is not None and not call.completed:
            # An interrupted provider request may still be billed. Keep its upper-bound charge
            # explicit rather than silently refunding an unknown external cost.
            call.budget.settle(call.reservation, call.estimate)
