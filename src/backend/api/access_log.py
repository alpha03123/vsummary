from __future__ import annotations

import logging
import re
from collections.abc import Iterable


class SuppressPathAccessLogFilter(logging.Filter):
    def __init__(self, *, paths: Iterable[str]) -> None:
        super().__init__()
        self._paths = frozenset(paths)

    def filter(self, record: logging.LogRecord) -> bool:
        request_path = _extract_request_path(record.getMessage())
        if request_path is None:
            return True
        return request_path not in self._paths


def install_access_log_filters() -> None:
    logger = logging.getLogger("uvicorn.access")
    for item in logger.filters:
        if isinstance(item, SuppressPathAccessLogFilter):
            return
    logger.addFilter(
        SuppressPathAccessLogFilter(
            paths={
                "/api/agent/memory/status",
                "/api/rag/models",
            },
        )
    )


def _extract_request_path(message: str) -> str | None:
    match = re.search(r'"[A-Z]+ (?P<target>\S+) HTTP/\d(?:\.\d)?"', message)
    if match is None:
        return None
    target = match.group("target")
    return target.split("?", 1)[0]
