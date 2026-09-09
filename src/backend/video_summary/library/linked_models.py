"""外部链接系列的领域值对象。

承载从 Bilibili 等外部站点拉取的「链接型系列」及其下属分P信息，
与本地导入系列的 DTO 解耦，避免在 RAG 流程中混淆本地与外部两种来源。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LinkedVideo:
    """外部链接视频的不可变值对象。

    表示一个外部平台的视频项。`source_id` 是平台内稳定标识，
    `item_index` 只用于一个源内存在多个可下载项的情形（例如 Bilibili 分 P）。

    Attributes:
        source_id: 平台内稳定视频标识。
        item_index: 同一 source_id 下的条目序号，从 1 开始。
        title: 视频标题。
        cover_url: 封面图 URL。
        duration_seconds: 视频时长（秒）。
        source_url: 原始外部链接。
        provider: 来源站点标识，默认 "bilibili"。
        download_key: 已生成下载任务的 key；尚未触发下载时为空字符串。
    """

    source_id: str
    item_index: int
    title: str
    cover_url: str
    duration_seconds: int
    source_url: str
    provider: str = "bilibili"
    download_key: str = ""

    @property
    def video_id(self) -> str:
        """返回在库内统一的 video_id。

        首项直接使用 `source_id`；后续项在尾部追加 `_p<item_index>`，
        保持既有 Bilibili 分 P 文件名不变。
        """
        return self.source_id if self.item_index == 1 else f"{self.source_id}_p{self.item_index}"


@dataclass(frozen=True)
class LinkedSeries:
    """外部链接系列的不可变值对象。

    把一个外部收藏夹/合集抽象成与本地 `LibrarySeriesDTO` 平级的系列单元，
    通过 `videos` 列表承载分P 顺序；`videos` 默认为空，
    待解析完成后再追加 `LinkedVideo` 项。

    Attributes:
        series_id: 库内统一的系列 ID。
        title: 系列标题（通常来自外部收藏夹名）。
        cover_url: 系列封面图 URL。
        source_url: 外部系列入口链接。
        is_agent_managed: 是否由 agent/MCP 自动化流程创建并管理。
        videos: 解析得到的分P 视频列表。
    """

    series_id: str
    title: str
    cover_url: str
    source_url: str
    is_agent_managed: bool = False
    videos: list[LinkedVideo] = field(default_factory=list)
