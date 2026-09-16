"""LiteLLM 兼容的本地图片消息构造辅助。"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Sequence


def build_multimodal_user_content(*, text: str, image_paths: Sequence[Path]) -> list[dict[str, object]]:
    """将文本和本地 JPEG 文件编码为 OpenAI 兼容的消息内容部件。"""
    content: list[dict[str, object]] = [{"type": "text", "text": text}]
    for path in image_paths:
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            raise ValueError(f"多模态输入只支持 JPEG：{path.name}")
        if not path.is_file():
            raise FileNotFoundError(f"多模态截图不存在：{path.name}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "format": "image/jpeg"},
            }
        )
    return content
