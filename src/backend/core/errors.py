"""Product-neutral domain errors shared across adapters and use cases."""

from __future__ import annotations


class ActiveJobConflictError(RuntimeError):
    """A resource cannot be mutated while a durable Job owns it."""


class UserVisibleError(RuntimeError):
    """An adapter-classified failure with a safe message for the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TemporaryServiceError(UserVisibleError):
    """An external service is temporarily unreachable; the job worker retries the job later."""

    def __init__(self, code: str, message: str, *, retry_after_seconds: int = 30):
        super().__init__(code, message)
        self.retry_after_seconds = retry_after_seconds
