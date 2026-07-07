from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

from backend.api.access_log import SuppressPathAccessLogFilter


class SuppressPathAccessLogFilterTests(unittest.TestCase):
    def test_suppresses_exact_memory_status_access_log(self) -> None:
        record = _build_record('127.0.0.1:63293 - "GET /api/agent/memory/status HTTP/1.1" 200 OK')
        log_filter = SuppressPathAccessLogFilter(paths={"/api/agent/memory/status"})

        self.assertFalse(log_filter.filter(record))

    def test_suppresses_memory_status_access_log_with_query_string(self) -> None:
        record = _build_record('127.0.0.1:63293 - "GET /api/agent/memory/status?scope=all HTTP/1.1" 200 OK')
        log_filter = SuppressPathAccessLogFilter(paths={"/api/agent/memory/status"})

        self.assertFalse(log_filter.filter(record))

    def test_keeps_other_access_logs(self) -> None:
        record = _build_record('127.0.0.1:63293 - "GET /api/agent/chat HTTP/1.1" 200 OK')
        log_filter = SuppressPathAccessLogFilter(paths={"/api/agent/memory/status"})

        self.assertTrue(log_filter.filter(record))

    def test_keeps_similar_prefix_paths(self) -> None:
        record = _build_record('127.0.0.1:63293 - "GET /api/agent/memory/status-extra HTTP/1.1" 200 OK')
        log_filter = SuppressPathAccessLogFilter(paths={"/api/agent/memory/status"})

        self.assertTrue(log_filter.filter(record))


def _build_record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
