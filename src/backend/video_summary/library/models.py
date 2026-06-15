"""视频库层对外暴露的 DTO 集合。

本模块定义「库」与「API 边界」之间传递的所有不可变 DTO，
包括链接解析结果、库/系列/视频卡片、各种视频制品（总结、转写、思维导图、
章节、知识卡片、笔记）以及 Workspace 工具状态。它们是文件系统内部表示
与外部消费方（FastAPI 路由、Agent）之间的稳定契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class BilibiliUrlInfoDTO:
    """Bilibili 链接解析的中间结果。

    `url_type` 当前恒为 "unknown"——具体是单视频、合集还是分P 的判定
    被延迟到 `LinkedVideoResolver` 完成，避免在解析阶段就硬编码分类。

    Attributes:
        url: 已规范化的原始链接。
        url_type: 链接类型占位字段，固定为 "unknown"。
    """

    url: str
    url_type: Literal["unknown"] = "unknown"


@dataclass(frozen=True)
class LibrarySeriesDTO:
    """库内一个系列的卡片级摘要。

    用于在「库面板」展示时一次性返回整组视频的轻量信息，
    不携带制品（总结、转写等）内容。

    Attributes:
        id: 系列唯一 ID。
        title: 系列标题。
        videos: 属于该系列的视频卡片列表。
        is_linked: 是否为外部链接型系列（区别于本地导入）。
        source_url: 外部入口链接；本地系列时为空字符串。
    """

    id: str
    title: str
    videos: list["LibraryVideoCardDTO"]
    is_linked: bool = False
    source_url: str = ""


@dataclass(frozen=True)
class LibraryVideoCardDTO:
    """库内单个视频的卡片级摘要。

    用于在系列面板与搜索结果中展示一条视频的元数据与处理状态，
    内容制品（总结、转写等）由其他 DTO 单独返回。

    Attributes:
        id: 视频唯一 ID。
        title: 视频标题。
        source_name: 源文件展示名（本地）或站点名（外部链接）。
        processed: 是否已生成至少一份制品（总结/转写/思维导图等）。
        status: 处理状态文本（如 "pending"/"ready"/"failed"），由用例层定义。
        source_type: 源类型，"video" 表示本地视频文件。
        is_linked: 是否来自外部链接（未实际下载到本地）。
        bilibili_bvid: Bilibili BV 号；非 B 站来源时为空字符串。
        bilibili_page: Bilibili 分P 序号；非分P 视频为 0。
        source_url: 外部入口链接；本地视频时为空字符串。
        provider: 外部站点标识；本地视频时为空字符串。
    """

    id: str
    title: str
    source_name: str
    processed: bool
    status: str
    source_type: str = "video"
    is_linked: bool = False
    bilibili_bvid: str = ""
    bilibili_page: int = 0
    source_url: str = ""
    provider: str = ""


@dataclass(frozen=True)
class WorkspaceDTO:
    """工作区基本信息。

    当前系统只存在一个工作区，但接口预留了多工作区扩展空间。
    工作区是所有「系列」的顶层容器，决定数据根目录的写入位置。

    Attributes:
        id: 工作区唯一 ID。
        title: 工作区标题。
    """

    id: str
    title: str


@dataclass(frozen=True)
class VideoLibraryDTO:
    """库面板的顶层视图。

    一次返回「工作区 + 全部系列」的快照，供前端 SPA 初始化使用。

    Attributes:
        workspace: 当前工作区基本信息。
        series: 工作区下所有系列（含空系列）。
    """

    workspace: WorkspaceDTO
    series: list[LibrarySeriesDTO]


@dataclass(frozen=True)
class VideoSourceDTO:
    """单个视频的源文件与产物目录信息。

    给到下游「预览/播放/转码」等子模块作为输入：源文件路径、输出目录、
    是否已经处理过。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        title: 视频标题。
        source_name: 源文件展示名。
        source_path: 源视频文件绝对路径。
        output_dir: 该视频制品（转写/总结/思维导图等）的输出根目录。
        processed: 是否已生成过制品。
        source_type: 源类型，默认 "video"。
        duration_seconds: 视频时长（秒）；未探测到则为 `None`。
    """

    series_id: str
    video_id: str
    title: str
    source_name: str
    source_path: Path
    output_dir: Path
    processed: bool
    source_type: str = "video"
    duration_seconds: float | None = None


@dataclass(frozen=True)
class VideoSummaryDTO:
    """单个视频的结构化总结。

    `summary` 是 LLM 产出的结构化字段（含要点、关键词、问答对、章节等），
    由总结用例从制品 JSON 文件读取后填入。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        title: 视频标题。
        summary: 结构化总结字段（具体键值由总结用例决定）。
    """

    series_id: str
    video_id: str
    title: str
    summary: dict[str, Any]


@dataclass(frozen=True)
class TranscriptSegmentDTO:
    """单条转写片段。

    描述一段连续语音对应的时间区间与文本；与 `domain.models.TranscriptSegment`
    字段相同，但作为库层 DTO 对外暴露。

    Attributes:
        start_seconds: 起始时间（秒）。
        end_seconds: 结束时间（秒）。
        text: 片段文本。
    """

    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class VideoTranscriptDTO:
    """单个视频的完整转写结果。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        title: 视频标题。
        duration_seconds: 视频总时长（秒）；未探测到则为 `None`。
        segments: 按时间顺序排列的转写片段列表。
    """

    series_id: str
    video_id: str
    title: str
    duration_seconds: float | None
    segments: list[TranscriptSegmentDTO]


@dataclass(frozen=True)
class VideoMindmapDTO:
    """单个视频的思维导图。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        title: 视频标题。
        mindmap: 思维导图节点/边数据；具体 schema 由生成用例决定。
    """

    series_id: str
    video_id: str
    title: str
    mindmap: dict[str, Any]


@dataclass(frozen=True)
class ChapterCardDTO:
    """单张章节卡。

    描述视频中的一个时间片段（章节），承载其总结、要点以及可点击跳转的时间戳。

    Attributes:
        id: 章节卡唯一 ID。
        title: 章节标题。
        summary: 章节总结文本。
        key_points: 要点列表。
        start_seconds: 起始时间（秒）；未对齐原始时间轴则为 `None`。
        end_seconds: 结束时间（秒）；未对齐原始时间轴则为 `None`。
        kind: 章节类型（如 "chapter"/"intro"/"summary" 等，由生成器定义）。
    """

    id: str
    title: str
    summary: str
    key_points: list[str]
    start_seconds: float | None
    end_seconds: float | None
    kind: str


@dataclass(frozen=True)
class VideoChapterCardsDTO:
    """单个视频的全部章节卡。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        title: 视频标题。
        cards: 章节卡列表，按视频内出现顺序排列。
    """

    series_id: str
    video_id: str
    title: str
    cards: list[ChapterCardDTO]


@dataclass(frozen=True)
class KnowledgeCardDTO:
    """单张知识卡。

    知识卡与章节卡是平行概念：知识卡偏向「实体/概念/问答」型的可重用单元，
    章节卡偏向「按时间切分」的视频片段。两者使用场景不同。

    Attributes:
        id: 知识卡唯一 ID。
        title: 知识卡标题。
        kind: 知识卡类型（如 "concept"/"entity"/"qa" 等，由生成器定义）。
        summary: 一句话摘要。
        details: 详细正文（Markdown）。
        tags: 人工/自动归类的标签列表。
        keywords: 关键词列表，用于检索增强。
        related_card_ids: 关联的其他知识卡 ID 列表。
    """

    id: str
    title: str
    kind: str
    summary: str
    details: str
    tags: list[str]
    keywords: list[str]
    related_card_ids: list[str]


@dataclass(frozen=True)
class VideoKnowledgeCardsDTO:
    """单个视频的全部知识卡。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        title: 视频标题。
        cards: 知识卡列表。
    """

    series_id: str
    video_id: str
    title: str
    cards: list[KnowledgeCardDTO]


@dataclass(frozen=True)
class VideoNoteDTO:
    """单条用户/AI 笔记。

    Attributes:
        id: 笔记唯一 ID。
        title: 笔记标题。
        content: 笔记正文（Markdown）。
        source: 笔记来源（如 "user"/"ai"/"import"）。
        created_at: 创建时间（ISO 8601 字符串）。
        updated_at: 更新时间（ISO 8601 字符串）。
    """

    id: str
    title: str
    content: str
    source: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class VideoNotesDTO:
    """单个视频的笔记集合。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        title: 视频标题。
        notes: 笔记列表，按更新时间倒序。
    """

    series_id: str
    video_id: str
    title: str
    notes: list[VideoNoteDTO]


@dataclass(frozen=True)
class WorkspaceToolDTO:
    """工作区单个工具面板的状态。

    用于在 SPA 的工作区界面中渲染按钮、loading 与失败状态。

    Attributes:
        id: 工具 ID（与制品类型一一对应）。
        title: 工具按钮展示名。
        available: 工具当前是否可用（如依赖源文件存在）。
        generated: 是否已生成对应制品。
        status: 处理状态文本（"idle"/"running"/"ready"/"failed"）。
        preview_url: 预览图/文件 URL；没有则 `None`。
    """

    id: str
    title: str
    available: bool
    generated: bool
    status: str
    preview_url: str | None = None


@dataclass(frozen=True)
class VideoWorkspaceToolsDTO:
    """单个视频工作区全部工具的状态集合。

    把工具栏所需的全部状态打包成一次接口返回，避免前端轮询多次。
    `ai_todo` 是当前给 AI 推荐的「下一步动作」提示文本。

    Attributes:
        series_id: 所属系列 ID。
        video_id: 视频唯一 ID。
        overview: 总览（总结）工具状态。
        knowledge_cards: 知识卡工具状态。
        mindmap: 思维导图工具状态。
        notes: 笔记工具状态。
        preview: 预览（封面/片段）工具状态。
        ai_todo: AI 推荐的「下一步动作」提示文本。
    """

    series_id: str
    video_id: str
    overview: WorkspaceToolDTO
    knowledge_cards: WorkspaceToolDTO
    mindmap: WorkspaceToolDTO
    notes: WorkspaceToolDTO
    preview: WorkspaceToolDTO
    ai_todo: str
