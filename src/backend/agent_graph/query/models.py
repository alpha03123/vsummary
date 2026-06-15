"""系列级 query 处理与 answer 合成阶段共用的 Pydantic 数据模型。

集中维护"用户查询改写结果"、"单条 RAG 检索命中"以及"系列回答结构化
输出"三类 DTO，供 `SeriesQueryProcessor` / `SeriesAnswerSynthesizer` /
`SeriesRetrievalService` 之间的数据传递使用。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SeriesQueryUnderstanding(BaseModel):
    """`SeriesQueryProcessor` 把用户原始问题改写后的查询合同。

    Attributes:
        normalized_query: 经改写、便于下游统一检索的标准查询字符串。
        subqueries: 把复杂问题拆出的子问题列表；下游可并发检索。
        filters: 检索过滤条件字典（如 `series_id`、`video_ids` 等）；
            调用方会在其后注入 `series_id` 保证检索不会跨系列。
    """

    normalized_query: str
    subqueries: list[str] = Field(default_factory=list)
    filters: dict[str, object] = Field(default_factory=dict)


class RetrievalHit(BaseModel):
    """一次 RAG 检索返回的单条命中证据。

    Attributes:
        evidence_id: 内部唯一证据 ID（用于跨阶段引用与 inline citation 解析）。
        doc_id: 来源文档 ID（LanceDB 中的原始 ID）。
        series_id: 所属系列 ID；用于按系列过滤。
        video_id: 命中所属视频 ID；跨系列资料（如检索扩展来源）时为 `None`。
        source_type: 来源类型枚举字符串（如 `transcript_chunk` /
            `summary_global` / `web_search` 等），用于决定如何渲染为 citation。
        source_family: 来源族大类（如 `local` / `web` / `summary`），
            便于上游快速分流处理。
        title: 命中标题（通常是视频标题或网页标题）。
        chapter_title: 命中所属章节标题；未命中具体章节时为 `None`。
        start_seconds: 命中在视频内的起始时间（秒）；不适用时为 `None`。
        end_seconds: 命中在视频内的结束时间（秒）；不适用时为 `None`。
        score: 检索相似度分数，越大越相关；默认 0.0。
        text: 命中的原始文本片段（用于构造 snippet 展示或 LLM 引用）。
    """

    evidence_id: str
    doc_id: str
    series_id: str
    video_id: str | None = None
    source_type: str
    source_family: str
    title: str
    chapter_title: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    score: float = 0.0
    text: str = ""


class SeriesAnswerPayload(BaseModel):
    """系列级 answer synthesis 的结构化输出。

    Attributes:
        answer: 完整的 Markdown 回答正文；不含任何内部 ID（如 e1、e2、doc_id）。
        citations: 本次回答实际使用到的 `evidence_items` 中 `evidence_id` 列表；
            用于内部追踪与渲染 footnote，不直接出现在 `answer` 文本里。
        used_source_types: 本次回答使用到的来源类型列表（如 `summary` /
            `transcript_chunk` / `web_search`），便于前端按类型过滤展示。
    """

    answer: str
    citations: list[str] = Field(default_factory=list, description="使用到的 evidence_items evidence_id 列表。")
    used_source_types: list[str] = Field(default_factory=list)
