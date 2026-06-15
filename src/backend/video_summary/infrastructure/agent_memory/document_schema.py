"""RAG 索引与系列目录的 Pydantic 数据模型。

定义写入 LanceDB 的 `RetrievalDocumentRecord` 与系列级目录的轻量索引
`SeriesCatalogPayload`，作为产物序列化与跨层传输的契约。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SeriesCatalogVideoRecord(BaseModel):
    """系列目录中单条视频的轻量索引记录。

    仅保存 Agent 在 series scope 下做概览检索所需的字段，避免重复读取
    完整的转写/总结制品。
    """

    video_id: str
    title: str
    one_sentence_summary: str = ""
    chapter_titles: list[str] = Field(default_factory=list)
    processed: bool = False


class SeriesCatalogPayload(BaseModel):
    """系列目录的根级索引快照，供 series scope 的检索与展示使用。

    Attributes:
        series_id: 所属系列 ID。
        series_title: 系列标题（仅用于元数据展示）。
        videos: 系列下视频的轻量记录列表。
        updated_at: 目录生成时的 ISO 时间戳，用于缓存一致性判断。
    """

    series_id: str
    series_title: str
    videos: list[SeriesCatalogVideoRecord] = Field(default_factory=list)
    updated_at: str


class RetrievalDocumentRecord(BaseModel):
    """写入向量数据库的检索文档记录。

    一条记录对应 LanceDB 中一个被索引的分片：`text` 是嵌入与检索的正文，
    其余字段构成 metadata 用于过滤、引用回溯与证据拼装。

    Attributes:
        doc_id: 文档唯一 ID（与 `doc_id` metadata 字段相同，方便 LanceDB 主键定位）。
        series_id: 所属系列 ID，用于 series 级过滤。
        video_id: 所属视频 ID；非视频级制品（如系列目录）时为空字符串。
        title: 视频标题，用于证据展示。
        source_type: 来源细类（如 `summary_global` / `summary_chapter` /
            `transcript_chunk` / `note` / `knowledge_card`）。
        source_family: 来源大类（`summary` / `transcript` / `notes` / `cards`），
            用于 source_tags 过滤。
        chapter_title: 仅 summary_chapter 类型时填充的章节标题。
        start_seconds: 转写/章节片段的起始时间；其他来源则为 `None`。
        end_seconds: 转写/章节片段的结束时间；其他来源则为 `None`。
        note_id: 仅 note 类型时填充的笔记 ID。
        note_source: 仅 note 类型时填充的笔记来源（用户/AI）。
        card_id: 仅 knowledge_card 类型时填充的卡片 ID。
        card_kind: 仅 knowledge_card 类型时填充的卡片类型。
        text: 被嵌入的正文内容。
    """

    doc_id: str
    series_id: str
    video_id: str = ""
    title: str = ""
    source_type: str
    source_family: str
    chapter_title: str = ""
    start_seconds: float | None = None
    end_seconds: float | None = None
    note_id: str = ""
    note_source: str = ""
    card_id: str = ""
    card_kind: str = ""
    text: str
