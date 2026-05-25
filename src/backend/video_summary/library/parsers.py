from __future__ import annotations

import re

from backend.video_summary.library.models import BilibiliUrlInfoDTO
from backend.video_summary.library.ports import BilibiliUrlParser


class DefaultBilibiliUrlParser(BilibiliUrlParser):
    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        normalized = url.strip()
        if not normalized:
            raise ValueError("URL 不能为空。请输入完整的 Bilibili 链接。")
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
            normalized = f"https://{normalized.lstrip('/')}"
        return BilibiliUrlInfoDTO(url=normalized)
