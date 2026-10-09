"""yt-dlp 平台共享的 Cookie 文件工具。"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar
from backend.shared.request_pacing import RequestPacer


T = TypeVar("T")


def request_sleep_flags(pacer: RequestPacer | None) -> list[str]:
    if pacer is None:
        return []
    delay = str(pacer.interval_seconds)
    return ["--sleep-requests", delay, "--sleep-interval", delay]


class CookieRequiredError(RuntimeError):
    """An extractor explicitly reported that authentication is required."""


def requires_cookie(error: Exception) -> bool:
    if isinstance(error, CookieRequiredError):
        return True
    message = str(error).lower()
    # yt-dlp CLI exposes extractor errors as text, not structured error codes.
    return any(marker in message for marker in (
        "login required", "log in to", "please log in", "sign in to", "not logged in",
        "only available when logged in", "fresh cookies", "cookies are needed",
        "cookies are no longer valid", "cookie_required", "for the authentication",
        "only available for registered users", "http error 401", "401 unauthorized",
    ))


def is_format_unavailable(error: Exception) -> bool:
    message = str(error).lower()
    return "requested format is not available" in message or "no video formats" in message


def run_with_cookie_fallback(operation: Callable[[str], T], cookie: str) -> T:
    """Try anonymously, then retry an explicit authentication failure once."""
    try:
        return operation("")
    except InterruptedError:
        raise
    except Exception as error:
        if not cookie.strip() or not requires_cookie(error):
            raise
    return operation(cookie)


@contextmanager
def temporary_cookie_file(cookie: str, domain: str) -> Iterator[Path | None]:
    path = write_cookies_file(cookie, domain)
    if cookie.strip() and path is None:
        raise ValueError("Configured Cookie contains no cookie pairs.")
    try:
        yield path
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def parse_cookie_pairs(cookie: str) -> list[tuple[str, str]]:
    """解析 HTTP Cookie header，保留有名称的键值对。"""
    pairs: list[tuple[str, str]] = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        normalized_name = name.strip()
        if normalized_name:
            pairs.append((normalized_name, value.strip()))
    return pairs


def write_cookies_file(cookie: str, domain: str) -> Path | None:
    """将 Cookie header 写为 yt-dlp 可读取的 Netscape 文件。"""
    pairs = parse_cookie_pairs(cookie)
    if not pairs:
        return None
    normalized_domain = domain.strip().lstrip(".")
    if not normalized_domain:
        raise ValueError("cookie domain must not be blank")
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".cookies.txt")
    with handle:
        handle.write("# Netscape HTTP Cookie File\n")
        for name, value in pairs:
            handle.write(f".{normalized_domain}\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
    return Path(handle.name)
