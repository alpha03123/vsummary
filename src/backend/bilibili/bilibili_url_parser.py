from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class BilibiliUrlInfo:
    url_type: Literal["season", "series", "video"]
    uid: int | None = None
    sid: int | None = None
    bvid: str | None = None


class BilibiliUrlParseError(ValueError):
    """无法识别的 Bilibili URL。"""


def parse_bilibili_url(url: str) -> BilibiliUrlInfo:
    url = url.strip()
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path.rstrip("/")
    params = parse_qs(parsed.query)

    bvid_match = re.search(r"(BV[a-zA-Z0-9]{10})", path)
    if bvid_match and host in ("www.bilibili.com", "m.bilibili.com", ""):
      return BilibiliUrlInfo(url_type="video", bvid=bvid_match.group(1))

    if host == "space.bilibili.com":
        path_parts = [part for part in path.split("/") if part]
        if not path_parts:
            raise BilibiliUrlParseError(f"无法从 URL 中提取 UID：{url}")
        try:
            uid = int(path_parts[0])
        except ValueError as exc:
            raise BilibiliUrlParseError(f"UID 格式错误：{path_parts[0]}") from exc

        sid_values = params.get("sid")
        if not sid_values:
            raise BilibiliUrlParseError(f"URL 中缺少 sid 参数：{url}")
        try:
            sid = int(sid_values[0])
        except ValueError as exc:
            raise BilibiliUrlParseError(f"sid 格式错误：{sid_values[0]}") from exc

        if "collectiondetail" in path:
            return BilibiliUrlInfo(url_type="season", uid=uid, sid=sid)
        if "seriesdetail" in path:
            return BilibiliUrlInfo(url_type="series", uid=uid, sid=sid)

        raise BilibiliUrlParseError(f"未知的 space.bilibili.com 路径类型：{path}")

    raise BilibiliUrlParseError(
        f"无法识别的 Bilibili URL（仅支持 space.bilibili.com 合集和 www.bilibili.com/video）：{url}"
    )
