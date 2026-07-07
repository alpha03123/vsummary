"""uvicorn 访问日志过滤器。

对高频轮询的 API 路径（如 Agent 内存状态、RAG 模型状态）屏蔽访问日志，
避免控制台被周期性请求刷屏。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable


class SuppressPathAccessLogFilter(logging.Filter):
    """按请求路径屏蔽 uvicorn 访问日志的过滤器。

    给定一组路径，当访问日志条目命中其中任何一条时，该条目被丢弃（返回 False），
    其余路径正常输出。路径集合在构造时冻结，不可变。

    业务意图：前端会高频轮询某些状态端点，这些日志没有排查价值却会淹没控制台。
    """

    def __init__(self, *, paths: Iterable[str]) -> None:
        super().__init__()
        self._paths = frozenset(paths)

    def filter(self, record: logging.LogRecord) -> bool:
        """判断一条日志记录是否应输出。

        Args:
            record: uvicorn 访问日志记录。

        Returns:
            True 表示输出该日志；False 表示丢弃（路径在黑名单中）。
        """
        request_path = _extract_request_path(record.getMessage())
        if request_path is None:
            return True
        return request_path not in self._paths


def install_access_log_filters() -> None:
    """安装访问日志过滤器到 uvicorn.access logger。

    安装前检查是否已存在同类型过滤器，避免重复添加。
    当前屏蔽路径：``/api/agent/memory/status``、``/api/rag/models``。
    """
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
    """从 uvicorn 访问日志行中提取请求路径。

    Args:
        message: uvicorn 格式化后的访问日志行。

    Returns:
        提取到的请求路径（不含 query string）；若无法解析则返回 None。
    """
    match = re.search(r'"[A-Z]+ (?P<target>\S+) HTTP/\d(?:\.\d)?"', message)
    if match is None:
        return None
    target = match.group("target")
    return target.split("?", 1)[0]
