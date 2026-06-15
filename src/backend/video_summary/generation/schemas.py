"""生成层 Pydantic 载荷模型。

定义 LLM 输出与制品之间互相转换所用的 DTO 形态：章节、整篇总结、
思维导图节点、转写片段、转写增强结果。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SummaryChapterPayload(BaseModel):
    """单章节总结的载荷模型。

    Attributes:
        id: 章节业务 ID，对应前端锚点定位。
        title: 章节标题。
        start_seconds: 章节起始时间（秒）。
        end_seconds: 章节结束时间（秒）。
        summary: 章节小结文本。
        key_points: 章节要点列表。
    """

    id: str
    title: str
    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)


class SummaryPayload(BaseModel):
    """整篇视频总结的载荷模型。

    Attributes:
        title: 视频标题。
        one_sentence_summary: 一句话总结。
        core_problem: 视频核心要解决的问题。
        chapters: 章节总结列表。
        key_takeaways: 关键结论列表。
    """

    title: str
    one_sentence_summary: str = ""
    core_problem: str = ""
    chapters: list[SummaryChapterPayload] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)


class MindmapNodePayload(BaseModel):
    """思维导图节点的载荷模型（递归结构）。

    Attributes:
        id: 节点业务 ID。
        title: 节点标题。
        summary: 节点摘要文本。
        start_seconds: 节点对应的时间起点（秒）；无时间锚点时为 0.0。
        end_seconds: 节点对应的时间终点（秒）；无时间锚点时为 0.0。
        children: 子节点列表。
    """

    id: str
    title: str
    summary: str = ""
    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    children: list["MindmapNodePayload"] = Field(default_factory=list)


class TranscriptSegmentPayload(BaseModel):
    """转写片段的载荷模型。

    Attributes:
        start_seconds: 片段起始时间（秒）。
        end_seconds: 片段结束时间（秒）。
        text: 片段文本。
    """

    start_seconds: float = Field(default=0.0)
    end_seconds: float = Field(default=0.0)
    text: str


class TranscriptEnhancementPayload(BaseModel):
    """转写增强结果的载荷模型。

    Attributes:
        segments: 增强后的转写片段列表。
    """

    segments: list[TranscriptSegmentPayload] = Field(default_factory=list)
