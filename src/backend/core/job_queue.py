"""Host admission errors shared by API and scheduling implementations."""


class JobQueueFull(RuntimeError):
    """The host cannot admit more work right now."""
