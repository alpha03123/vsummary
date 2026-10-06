"""Public generation failures that can be shown without provider details."""


class MediaSourceUnavailableError(LookupError):
    """Generation requires media that has not been retained or uploaded."""
