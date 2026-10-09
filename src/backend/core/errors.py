"""Product-neutral domain errors shared across adapters and use cases."""

from __future__ import annotations


class ActiveJobConflictError(RuntimeError):
    """A resource cannot be mutated while a durable Job owns it."""


class UserVisibleError(RuntimeError):
    """An adapter-classified failure with a safe message for the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
