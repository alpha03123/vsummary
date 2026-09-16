"""视觉制品在生成层的窄数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlannedChapterFrame:
    """已通过章节范围校验、等待 ffmpeg 抽取的截图计划。"""

    chapter_id: str
    timestamp_seconds: float
    image_filename: str


@dataclass(frozen=True)
class ExtractedChapterFrame:
    """一次生成中已由 ffmpeg 写入 staging 的章节截图。"""

    chapter_id: str
    timestamp_seconds: float
    image_filename: str
    path: Path
