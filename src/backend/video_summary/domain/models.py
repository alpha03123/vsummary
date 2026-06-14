"""视频资产领域值对象。

本模块只包含不可变的领域数据类型，不依赖任何基础设施层。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VideoAsset:
    """视频资产不可变值对象。

    表示一个已索引的视频条目：源文件路径 + 标题 + 时长。
    一旦构造不允许修改，作为业务键比较的标识由 `source_path` 承担。
    """

    source_path: Path
    title: str
    duration_seconds: float


@dataclass(frozen=True)
class TranscriptSegment:
    """单条转写片段。

    Attributes:
        start_seconds: 起始时间（秒）。
        end_seconds: 结束时间（秒）。
        text: 片段文本。
    """

    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class Transcript:
    """视频转写结果。

    Attributes:
        language: 检测到的语言代码（如 "zh"、"en"）。
        segments: 按时间顺序排列的转写片段列表。

    Properties:
        full_text: 把所有片段按换行拼接的纯文本，自动跳过空片段。
    """

    language: str
    segments: list[TranscriptSegment]

    @property
    def full_text(self) -> str:
        return "\n".join(segment.text.strip() for segment in self.segments if segment.text.strip())


@dataclass(frozen=True)
class SummaryDocument:
    """结构化总结文档。

    把视频总结拆成可独立消费的三部分：人类可读的 Markdown、
    机器可读的结构化字段、知识图谱思维导图（可选）。

    Attributes:
        markdown: 人类可读的总结 Markdown 文本。
        summary_data: 结构化字段（如要点、关键词、问答对）。
        mindmap_data: 思维导图节点/边数据，可能为空。
    """

    markdown: str
    summary_data: dict[str, Any]
    mindmap_data: dict[str, Any] | None = None
