from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from backend.video_summary.library.models import BilibiliUrlInfoDTO
from backend.video_summary.library.ports import BilibiliUrlParser


class DefaultBilibiliUrlParser(BilibiliUrlParser):
    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        url = url.strip()
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
                raise ValueError(f"无法从 URL 中提取 UID：{url}")
            try:
                uid = int(path_parts[0])
            except ValueError as exc:
                raise ValueError(f"UID 格式错误：{path_parts[0]}") from exc

            sid_values = params.get("sid")
            if not sid_values:
                raise ValueError(f"URL 中缺少 sid 参数：{url}")
            try:
                sid = int(sid_values[0])
            except ValueError as exc:
                raise ValueError(f"sid 格式错误：{sid_values[0]}") from exc

            if "collectiondetail" in path:
                return BilibiliUrlInfoDTO(url_type="season", uid=uid, sid=sid)
            if "seriesdetail" in path:
                return BilibiliUrlInfoDTO(url_type="series", uid=uid, sid=sid)

            raise ValueError(f"未知的 space.bilibili.com 路径类型：{path}")

        raise ValueError(
            f"无法识别的 Bilibili URL（仅支持 space.bilibili.com 合集和 www.bilibili.com/video）：{url}"
        )

