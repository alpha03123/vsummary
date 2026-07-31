"""Bilibili yt-dlp 访问所需的共享认证与代理工具。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

BILIBILI_USER_AGENT = "Mozilla/5.0"
BILIBILI_COOKIE_ENV = "BILIBILI_COOKIE"
BILIBILI_SESSDATA_ENV = "BILIBILI_SESSDATA"
BILIBILI_YTDLP_PROXY_ENV = "BILIBILI_YTDLP_PROXY"


def load_bilibili_headers(bvid: str) -> dict[str, str]:
    """构造访问 Bilibili 视频页/API 时使用的基础请求头。"""
    cookie = os.environ.get(BILIBILI_COOKIE_ENV, "").strip()
    if not cookie:
        sessdata = os.environ.get(BILIBILI_SESSDATA_ENV, "").strip()
        cookie = f"SESSDATA={sessdata}" if sessdata else ""
    headers = {
        "User-Agent": BILIBILI_USER_AGENT,
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def build_yt_dlp_add_header_flags(headers: dict[str, str]) -> list[str]:
    """把 yt-dlp Python/CLI 共用的 headers 转成 CLI 参数。"""
    flags: list[str] = []
    for key, value in headers.items():
        if not value:
            continue
        flags.extend(["--add-header", f"{key}:{value}"])
    return flags


def build_yt_dlp_proxy_flags() -> list[str]:
    """把 Bilibili yt-dlp 代理配置转成 CLI 参数。"""
    proxy = resolve_yt_dlp_proxy()
    return [] if proxy is None else ["--proxy", proxy]


def resolve_yt_dlp_proxy() -> str | None:
    """读取 Bilibili yt-dlp 代理配置；direct/none/off 表示显式直连。"""
    raw_proxy = os.environ.get(BILIBILI_YTDLP_PROXY_ENV)
    if raw_proxy is None or not raw_proxy.strip():
        return None
    proxy = raw_proxy.strip()
    return "" if proxy.lower() in {"direct", "none", "off"} else proxy


def write_bilibili_cookies_file(cookie: str) -> Path | None:
    """把 Cookie header 写成 yt-dlp 支持的 Netscape cookie 文件。"""
    if not cookie.strip():
        return None
    cookie_pairs = parse_cookie_pairs(cookie)
    if not cookie_pairs:
        return None
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".cookies.txt")
    with handle:
        handle.write("# Netscape HTTP Cookie File\n")
        for name, value in cookie_pairs:
            handle.write(f".bilibili.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
    return Path(handle.name)


def parse_cookie_pairs(cookie: str) -> list[tuple[str, str]]:
    """解析 HTTP Cookie header，保留有名称的键值对。"""
    pairs: list[tuple[str, str]] = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        normalized_name = name.strip()
        normalized_value = value.strip()
        if normalized_name:
            pairs.append((normalized_name, normalized_value))
    return pairs
