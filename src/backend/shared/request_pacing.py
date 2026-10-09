"""Coordinate platform request starts across threads and local worker processes."""

import json
import math
import time
from pathlib import Path
from collections.abc import Callable

from filelock import FileLock

from backend.shared.filesystem import atomic_write_text


CANCELLATION_POLL_SECONDS = 0.1


class RequestPacer:
    def __init__(self, *, interval_seconds: float, state_path: Path):
        if not math.isfinite(interval_seconds) or interval_seconds < 0:
            raise ValueError("Request interval must be finite and non-negative.")
        self.interval_seconds = interval_seconds
        self._state_path = state_path
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(state_path.with_suffix(".lock")))

    def wait(self, check_cancelled: Callable[[], None] | None = None) -> None:
        if self.interval_seconds == 0:
            if check_cancelled:
                check_cancelled()
            return
        with self._lock:
            last = json.loads(self._state_path.read_text(encoding="utf-8"))["started_at"] if self._state_path.exists() else None
            while True:
                if check_cancelled:
                    check_cancelled()
                remaining = 0 if last is None else last + self.interval_seconds - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, CANCELLATION_POLL_SECONDS))
            atomic_write_text(self._state_path, json.dumps({"started_at": time.time()}))
