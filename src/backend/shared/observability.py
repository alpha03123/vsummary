"""默认启用的结构化应用日志与执行上下文。"""

from __future__ import annotations

import json
import logging
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator


_REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_TASK_ID: ContextVar[str | None] = ContextVar("task_id", default=None)
_HANDLER_NAME = "vsummary-json-file"


class JsonLineFormatter(logging.Formatter):
    """把日志记录编码为一行 JSON，保留异常原因链与调用栈。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _REQUEST_ID.get(),
            "task_id": _TASK_ID.get(),
        }
        for name in (
            "event",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "command",
            "returncode",
            "stderr",
            "video_path",
            "timestamp_seconds",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            error = record.exc_info[1]
            if isinstance(error, subprocess.CalledProcessError):
                payload.setdefault("command", error.cmd)
                payload.setdefault("returncode", error.returncode)
                if error.stderr:
                    payload.setdefault("stderr", _decode_process_output(error.stderr))
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _decode_process_output(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def configure_application_logging(root_dir: Path) -> Path:
    """为全部 ``backend.*`` 日志器配置默认 JSON Lines 文件输出。"""
    log_path = root_dir / "logs" / "app.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("backend")
    logger.setLevel(logging.INFO)

    for handler in list(logger.handlers):
        if getattr(handler, "name", None) == _HANDLER_NAME:
            if getattr(handler, "baseFilename", None) == str(log_path.resolve()):
                return log_path
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.name = _HANDLER_NAME
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return log_path


def close_application_logging(root_dir: Path) -> None:
    """关闭指定应用根目录的文件 handler，释放 Windows 文件句柄。"""
    expected_path = str((root_dir / "logs" / "app.jsonl").resolve())
    logger = logging.getLogger("backend")
    for handler in list(logger.handlers):
        if getattr(handler, "baseFilename", None) == expected_path:
            logger.removeHandler(handler)
            handler.close()


@contextmanager
def bind_request_id(request_id: str) -> Iterator[None]:
    """在当前请求及其派生任务内绑定请求关联 ID。"""
    token = _REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)


@contextmanager
def bind_task_id(task_id: str) -> Iterator[None]:
    """在当前生成任务内绑定任务关联 ID。"""
    token = _TASK_ID.set(task_id)
    try:
        yield
    finally:
        _TASK_ID.reset(token)
