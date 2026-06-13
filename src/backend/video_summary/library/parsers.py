from __future__ import annotations

import re
from urllib.parse import urlparse

from backend.video_summary.library.models import BilibiliUrlInfoDTO
from backend.video_summary.library.ports import BilibiliUrlParser


class DefaultBilibiliUrlParser(BilibiliUrlParser):
    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        # 原始 parse 逻辑（已注释）：无法识别 IDN 编码的 mangled URL。
        # normalized = url.strip()
        # if not normalized:
        #     raise ValueError("URL 不能为空。请输入完整的 Bilibili 链接。")
        # if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
        #     normalized = f"https://{normalized.lstrip('/')}"
        # return BilibiliUrlInfoDTO(url=normalized)
        normalized = url.strip()
        if not normalized:
            raise ValueError("URL 不能为空。请输入完整的 Bilibili 链接。")
        # 新增：检测 IDN mangled URL。当原始链接经微信/QQ/输入法转发携带
        # 全角或不可见字符时，下游某层会把整个 scheme+host 当 IDN 域名编码，
        # 导致 path 起点变成 //。这里把原始 URL 从 path 里还原出来。
        parsed_url = urlparse(normalized)
        if parsed_url.path.startswith("//"):
            inner = parsed_url.path.lstrip("/")
            if inner.startswith(("http://", "https://")):
                normalized = inner
            else:
                normalized = f"https://{inner}"
            if parsed_url.query:
                normalized = f"{normalized}?{parsed_url.query}"
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
            normalized = f"https://{normalized.lstrip('/')}"
        return BilibiliUrlInfoDTO(url=normalized)
