from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import unittest
from pathlib import Path

from backend.shared.observability import (
    bind_request_id,
    bind_task_id,
    close_application_logging,
    configure_application_logging,
)


class ApplicationLoggingTests(unittest.TestCase):
    def test_records_context_and_original_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_dir = Path(directory)
            log_path = configure_application_logging(root_dir)
            logger = logging.getLogger("backend.test.observability")
            try:
                with bind_request_id("request-1"), bind_task_id("series/video"):
                    try:
                        raise ValueError("original failure")
                    except ValueError:
                        logger.exception("test failure", extra={"event": "test_failed"})

                record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(record["request_id"], "request-1")
                self.assertEqual(record["task_id"], "series/video")
                self.assertEqual(record["event"], "test_failed")
                self.assertIn("ValueError: original failure", record["exception"])
            finally:
                close_application_logging(root_dir)

    def test_extracts_original_subprocess_failure_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root_dir = Path(directory)
            log_path = configure_application_logging(root_dir)
            logger = logging.getLogger("backend.test.observability")
            try:
                try:
                    raise subprocess.CalledProcessError(
                        -22,
                        ["ffmpeg", "-ss", "nan"],
                        stderr=b"Invalid duration for option ss: nan",
                    )
                except subprocess.CalledProcessError:
                    logger.exception("subprocess failed")

                record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(record["returncode"], -22)
                self.assertEqual(record["command"], ["ffmpeg", "-ss", "nan"])
                self.assertEqual(record["stderr"], "Invalid duration for option ss: nan")
            finally:
                close_application_logging(root_dir)


if __name__ == "__main__":
    unittest.main()
