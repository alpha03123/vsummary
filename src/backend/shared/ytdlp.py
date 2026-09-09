"""yt-dlp 平台共享的 Cookie 文件工具。"""

from __future__ import annotations

import tempfile
from pathlib import Path


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
