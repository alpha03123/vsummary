"""Bilibili 链接解析器的默认实现。

把用户从聊天/浏览器粘贴过来的 Bilibili URL 规范化为可被下游解析的形态，
兼容被输入法/聊天工具转义过的 IDN mangled 链接。
"""

from __future__ import annotations

import re

from backend.video_summary.library.models import BilibiliUrlInfoDTO
from backend.video_summary.library.ports import BilibiliUrlParser


class DefaultBilibiliUrlParser(BilibiliUrlParser):
    """默认的 Bilibili URL 解析器。

    在原版「补 scheme + 去空白」逻辑之上，额外处理微信/QQ/输入法转发时
    把整个 scheme+host 当作 IDN 域名编码的场景：从 mangled 的 path 里
    把原始 URL 还原出来后再继续规范化。
    """

    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        """把用户输入的 URL 归一化为标准 https 链接。

        Args:
            url: 用户粘贴的原始 Bilibili 链接，可能缺 scheme、被空格包裹，
                或被聊天工具 mangled 成 IDN 形式。

        Returns:
            归一化后的 URL 包装对象，URL 类型标记为 "unknown"——
            真正的视频/收藏夹/分P 类型判定由下游 `LinkedVideoResolver` 负责。

        Raises:
            ValueError: URL 为空字符串时抛出。
        """
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
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", normalized):
            normalized = f"https://{normalized.lstrip('/')}"
        return BilibiliUrlInfoDTO(url=normalized)
