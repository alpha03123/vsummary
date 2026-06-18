"""视频库层的 Protocol 端口集合。

把「库」对外暴露的能力以 Protocol 类型声明，使用方（API 路由、Agent 用例）
按接口注入具体实现；具体实现位于 `infrastructure/` 子包，本模块不依赖任何
具体实现，便于在测试中替换。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.library.models import (
    BilibiliUrlInfoDTO,
    KnowledgeCardDTO,
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoChapterCardsDTO,
    VideoKnowledgeCardsDTO,
    VideoMindmapDTO,
    VideoNoteDTO,
    VideoNotesDTO,
    VideoSourceDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
    VideoWorkspaceToolsDTO,
    WorkspaceDTO,
)
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


class VideoLibraryReader(Protocol):
    """库内只读查询的端口。

    任何「根据 series_id/video_id 取一份制品」的用例都通过此接口读取；
    返回 `None` 表示制品尚未生成（区别于「生成失败」），调用方应据此
    决定走兜底分支（提示用户先生成）。
    """

    def get_workspace(self) -> WorkspaceDTO:
        """返回当前工作区基本信息。"""

    def list_series(self) -> list[LibrarySeriesDTO]:
        """列出工作区下所有系列（含空系列），按业务顺序排列。"""

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        """取视频的源文件与输出目录信息；不存在时返回 `None`。"""

    def get_video_summary(self, series_id: str, video_id: str) -> VideoSummaryDTO | None:
        """取视频的结构化总结制品；未生成则返回 `None`。"""

    def get_series_catalog(self, series_id: str) -> dict[str, object] | None:
        """取系列目录索引，供 Agent 在 series scope 下做概览检索。"""

    def get_video_transcript(self, series_id: str, video_id: str) -> VideoTranscriptDTO | None:
        """取视频的转写制品；未生成则返回 `None`。"""

    def get_video_mindmap(self, series_id: str, video_id: str) -> VideoMindmapDTO | None:
        """取视频的思维导图制品；未生成则返回 `None`。"""

    def get_video_chapter_cards(self, series_id: str, video_id: str) -> VideoChapterCardsDTO | None:
        """取视频的章节卡集合；未生成则返回 `None`。"""

    def get_video_knowledge_cards(self, series_id: str, video_id: str) -> VideoKnowledgeCardsDTO | None:
        """取视频的知识卡集合；未生成则返回 `None`。"""

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        """取视频的笔记集合；不存在则返回 `None`。"""

    def get_video_workspace_tools(self, series_id: str, video_id: str) -> VideoWorkspaceToolsDTO | None:
        """取视频工作区工具栏的完整状态。"""

    def get_series_mindmap(self, series_id: str) -> VideoMindmapDTO | None:
        """取系列的思维导图制品；未生成则返回 None。"""

    def get_series_dir(self, series_id: str) -> Path:
        """返回到系列工作区根目录的路径。"""


class VideoKnowledgeCardWriter(Protocol):
    """知识卡的写入端口。

    与读取端口分开声明，避免读路径被迫依赖写实现；
    知识卡的最终落盘动作（写 JSON + 触发索引刷新）由实现方一次性完成。
    """

    def save_video_knowledge_cards(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        cards: list[KnowledgeCardDTO],
    ) -> None:
        """把生成好的知识卡覆盖写入视频制品目录。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            title: 视频标题，仅用于制品元数据。
            cards: 待写入的知识卡列表。
        """


class VideoKnowledgeCardStore(VideoLibraryReader, VideoKnowledgeCardWriter, Protocol):
    """同时承担「读 + 写知识卡」两个职责的复合端口。

    Agent 用例只需依赖这一个接口即可完成知识卡的读/写闭环；
    该协议本身没有新增方法，作为「能力组合」的语义标记。
    """


class VideoKnowledgeCardStoreWithRefresh(VideoKnowledgeCardStore, Protocol):
    """带「写入后自动刷新 RAG 索引」能力的知识卡端口。

    写完知识卡需要让 Agent 即时检索到，所以部分实现会顺带触发索引 upsert；
    通过这个更窄的协议把这条依赖显式化，避免所有 `VideoKnowledgeCardStore`
    实现都被迫做索引刷新。
    """


class VideoNotesStore(Protocol):
    """视频笔记的 CRUD 端口。

    笔记由「用户手写」与「AI 生成」两种来源共存，本接口统一以 `source` 字段
    区分；实现侧负责把笔记 JSON 落到对应视频的制品目录。
    """

    def get_video_notes(self, series_id: str, video_id: str) -> VideoNotesDTO | None:
        """取视频的笔记集合；不存在则返回 `None`。"""

    def create_video_note(
        self,
        series_id: str,
        video_id: str,
        *,
        title: str,
        content: str,
        source: str,
    ) -> VideoNoteDTO | None:
        """新增一条笔记，返回落库后的 `VideoNoteDTO`（含分配 ID 与时间戳）。"""

    def update_video_note(
        self,
        series_id: str,
        video_id: str,
        note_id: str,
        *,
        title: str,
        content: str,
    ) -> VideoNoteDTO | None:
        """更新一条已存在的笔记；笔记不存在时返回 `None`。"""

    def delete_video_note(self, series_id: str, video_id: str, note_id: str) -> bool | None:
        """删除一条笔记；`True` 表示实际删除，`False` 表示未找到，`None` 由实现自定义语义。"""


class VideoImportStore(Protocol):
    """本地视频导入的端口。

    三种入口（新建系列/追加到沙盒/追加到既有系列）共用同一类实现，
    通过 `series_id` 是否为空来区分目标。
    """

    def import_local_series(self, *, title: str, files: list[tuple[str, object]]) -> LibrarySeriesDTO:
        """把一组本地视频导入为一个新系列。"""

    def import_local_playground_videos(self, *, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        """把本地视频导入到沙盒演练系列（无需选择系列）。"""

    def import_local_series_videos(self, *, series_id: str, files: list[tuple[str, object]]) -> list[LibraryVideoCardDTO]:
        """把本地视频追加到既有系列。"""


class VideoMutationStore(Protocol):
    """库内结构性变更的端口（删除系列/删除视频）。

    此类操作会级联清理制品目录与 RAG 索引，因此与只读端口分开。
    """

    def list_series(self) -> list[LibrarySeriesDTO]:
        """列出工作区下所有系列（供删除前展示）。"""

    def get_video_source(self, series_id: str, video_id: str) -> VideoSourceDTO | None:
        """取视频的源文件信息（删除前确认）。"""

    def delete_series(self, series_id: str) -> bool:
        """删除整个系列及其全部制品；返回是否实际删除了记录。"""

    def delete_video(self, series_id: str, video_id: str) -> bool:
        """删除单个视频及其全部制品；返回是否实际删除了记录。"""


class LinkedSeriesStore(Protocol):
    """外部链接系列的存储端口。

    链接型系列在本地只有「元数据 + 解析结果」没有真实文件，
    因此与本地视频的存储路径完全分离。
    """

    def save_linked_series(self, series: LinkedSeries) -> None:
        """保存一个链接型系列；存在则覆盖。"""

    def get_linked_series(self, series_id: str) -> LinkedSeries | None:
        """取链接型系列；不存在则返回 `None`。"""

    def delete_linked_series(self, series_id: str) -> bool:
        """删除一个链接型系列；返回是否实际删除了记录。"""


class LinkedSeriesResolverWorkspace(VideoLibraryReader, LinkedSeriesStore, Protocol):
    """链接型系列解析器所需的「读库 + 读写链接系列」复合端口。

    解析器在拿到 B 站返回结果后需要回查本地库（判断是否已存在），
    并把解析结果写回 `LinkedSeriesStore`，所以同时需要读和写能力。
    """


class VideoSummaryGenerator(Protocol):
    """视频总结的异步生成端口。

    实现方负责串起转写、LLM 总结、思维导图等子步骤；
    `transcript_enhancement_enabled=None` 表示「由实现方按默认配置决定」。
    """

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
    ) -> None:
        """为指定视频生成总结制品，副作用是落盘到视频制品目录。"""


class VideoMindmapGenerator(Protocol):
    """思维导图的异步生成端口。"""

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        summary_data: dict[str, object],
        transcript_text: str = "",
        progress_reporter: ProgressReporter | None = None,
    ) -> None:
        """基于已生成的总结数据生成思维导图，副作用是落盘到视频制品目录。

        Args:
            series_id: 所属系列 ID。
            video_id: 视频唯一 ID。
            summary_data: 总结数据字典，作为思维导图的输入。
            transcript_text: 转写全文文本，可选注入以丰富导图层级细节。
            progress_reporter: 可选进度上报端口；为 `None` 时不进行 SSE 上报。
        """


class SeriesMindmapGenerator(Protocol):
    """系列思维导图的异步生成端口。"""
    async def run(
        self,
        *,
        series_id: str,
        series_title: str,
        catalog: dict[str, object] | None,
        video_summaries: list[dict[str, object]],
    ) -> None:
        """基于系列目录与视频概况生成跨视频思维导图，落盘到系列制品目录。"""


class KnowledgeCardGenerator(Protocol):
    """知识卡的同步生成端口（纯函数式，不落盘）。

    与 `VideoMindmapGenerator` 不同，知识卡生成不写文件，由调用方拿到结果后
    通过 `VideoKnowledgeCardWriter` 落盘——这样可以走「先预览再保存」流程。
    """

    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardDTO]:
        """基于总结数据生成知识卡列表；不与文件系统交互。"""


class VideoGenerationProgressTracker(Protocol):
    """生成任务进度报告器的工厂端口。

    每次生成一个独立的 `task_id`，由实现方负责把进度事件路由到对应的
    `InMemoryProgressTracker`，前端再通过 SSE 订阅。
    """

    def create_reporter(self, task_id: str) -> ProgressReporter:
        """为指定任务 ID 创建一个进度报告器。"""


class LinkedVideoResolver(Protocol):
    """外部链接解析的端口。

    把 B 站 URL 拆成两种返回：合集（多视频） vs 单视频；
    失败语义由实现方定义（异常 vs 返回 `None`）。
    """

    async def resolve_series(self, url_info: BilibiliUrlInfoDTO) -> LinkedSeries:
        """把 URL 解析为链接型系列；非合集 URL 时行为由实现方决定。"""

    async def resolve_single_video(self, url_info: BilibiliUrlInfoDTO) -> LinkedVideo:
        """把 URL 解析为单个链接视频；非单视频 URL 时行为由实现方决定。"""


class BilibiliUrlParser(Protocol):
    """Bilibili URL 预处理的端口。

    真正的「视频/合集/分P」分类被推迟给 `LinkedVideoResolver`，
    本接口只做 URL 规范化（补 scheme、处理 IDN mangled 链接等）。
    """

    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        """把用户输入的 URL 归一化为可被下游解析的标准形态。"""


class LinkedVideoDownloadStarter(Protocol):
    """链接型视频下载启动的端口。

    启动一个后台下载任务并返回 `download_key`（用于后续查询进度）；
    不等待任务完成，调用方应通过 SSE 订阅进度。
    """

    def start(self, *, series_id: str, video: LinkedVideo) -> str:
        """为指定的链接视频启动下载，返回可被前端订阅的任务 key。"""


class WorkspaceIndexInvalidator(Protocol):
    """整个工作区 RAG 索引失效的端口。

    一次性让缓存失效，迫使下次访问时重建；与 `WorkspaceIndexRefresher`
    的差别在于：本接口是「标记失效」而不是「同步重建」。
    """

    def invalidate(self) -> None:
        """让整个工作区的 RAG 索引失效。"""


class WorkspaceIndexRefresher(Protocol):
    """整个工作区 RAG 索引的刷新端口。

    同时支持「全量刷新」「单视频 upsert」「按系列/视频删除」等细粒度操作，
    实现方负责把变更同步到 LanceDB。
    """

    def refresh_all(self) -> None:
        """全量重建工作区的 RAG 索引。"""

    def refresh(self) -> None:
        """增量刷新（仅处理自上次刷新以来变更的部分）。"""

    def upsert_video(self, series_id: str, video_id: str) -> None:
        """把单个视频的制品加入/更新到 RAG 索引。"""

    def delete_video(self, series_id: str, video_id: str) -> None:
        """从 RAG 索引中删除单个视频。"""

    def delete_series(self, series_id: str) -> None:
        """从 RAG 索引中删除整个系列。"""


class SeriesKnowledgeMemoryRefresher(Protocol):
    """系列级知识记忆的增量刷新端口。

    与 RAG 索引不同，知识记忆是「跨视频提炼出的可重用知识」，
    粒度更粗、刷新更慢，因此单独拆出一个端口。
    """

    def refresh(self, series_id: str, video_id: str):
        """为指定视频重新提炼系列级知识记忆。"""


class GenerationActivityChecker(Protocol):
    """生成任务活跃性查询的端口。

    供前端在用户尝试触发新生成前判断「是否已有进行中的任务」，
    避免并发触发造成制品覆盖。
    """

    def is_video_generation_active(self, series_id: str, video_id: str) -> bool:
        """判断指定视频是否仍有进行中的生成任务。"""

    def is_series_generation_active(self, series_id: str) -> bool:
        """判断指定系列是否仍有进行中的生成任务（任意视频）。"""
