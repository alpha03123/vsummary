from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from backend.video_summary.library.models import BilibiliUrlInfoDTO
from backend.video_summary.library.ports import BilibiliUrlParser


class DefaultBilibiliUrlParser(BilibiliUrlParser):
    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        url = _normalize_bilibili_url(url)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        bvid_match = re.search(r"(BV[a-zA-Z0-9]{10})", path)
        if bvid_match and host in ("www.bilibili.com", "m.bilibili.com", ""):
            return BilibiliUrlInfoDTO(url_type="video", bvid=bvid_match.group(1))

        if host == "space.bilibili.com":
            path_parts = [part for part in path.split("/") if part]
            if not path_parts:
                raise ValueError(f"无法从 URL 中提取 UID，请检查合集链接是否完整：{url}")
            try:
                uid = int(path_parts[0])
            except ValueError as exc:
                raise ValueError(f"UID 格式错误：{path_parts[0]}，请粘贴完整的 B 站空间合集链接。") from exc

            sid_values = params.get("sid")
            if not sid_values:
                raise ValueError(f"URL 中缺少 sid 参数，请确认这是合集详情页链接：{url}")
            try:
                sid = int(sid_values[0])
            except ValueError as exc:
                raise ValueError(f"sid 格式错误：{sid_values[0]}，请粘贴完整的合集详情页链接。") from exc

            if "collectiondetail" in path:
                return BilibiliUrlInfoDTO(url_type="season", uid=uid, sid=sid)
            if "seriesdetail" in path:
                return BilibiliUrlInfoDTO(url_type="series", uid=uid, sid=sid)

            raise ValueError(
                "无法识别该 B 站空间链接类型。请使用合集详情页链接，例如 "
                "https://space.bilibili.com/<uid>/lists/<sid>?type=season 或 "
                "https://space.bilibili.com/<uid>/lists/<sid>?type=series"
            )

        raise ValueError(
            "无法识别的 Bilibili URL。当前仅支持单视频链接和空间合集链接，例如 "
            "https://www.bilibili.com/video/BV... 或 "
            "https://space.bilibili.com/<uid>/lists/<sid>?type=season"
        )


def _normalize_bilibili_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("URL 不能为空。请输入完整的 Bilibili 链接。")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        normalized = f"https://{normalized.lstrip('/')}"
    return normalized
