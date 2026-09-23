"""Product-neutral domain errors shared across adapters and use cases."""

from __future__ import annotations


class ActiveJobConflictError(RuntimeError):
    """A resource cannot be mutated while a durable Job owns it."""
