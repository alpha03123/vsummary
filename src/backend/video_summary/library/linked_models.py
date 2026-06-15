"""外部链接系列的领域值对象。

承载从 Bilibili 等外部站点拉取的「链接型系列」及其下属分P信息，
与本地导入系列的 DTO 解耦，避免在 RAG 流程中混淆本地与外部两种来源。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LinkedVideo:
    """外部链接视频的不可变值对象。

    表示一个分P级别的 Bilibili 视频项；同一 `bvid` 下的不同分P
    共享 BV 号，但 `page` 与 `video_id` 派生规则区分。

    Attributes:
        bvid: Bilibili 视频 BV 号，作为同一稿件跨分P 的业务主键。
        page: 分P 序号（从 1 开始）。
        title: 视频标题。
        cover_url: 封面图 URL。
        duration_seconds: 视频时长（秒）。
        source_url: 原始外部链接。
        provider: 来源站点标识，默认 "bilibili"。
        download_key: 已生成下载任务的 key；尚未触发下载时为空字符串。
    """

    bvid: str
    page: int
    title: str
    cover_url: str
    duration_seconds: int
    source_url: str
    provider: str = "bilibili"
    download_key: str = ""

    @property
    def video_id(self) -> str:
        """返回在库内统一的 video_id。

        分P 1 直接使用 `bvid`；其他分P 在尾部追加 `_p<page>` 以保证唯一性。
        """
        return self.bvid if self.page == 1 else f"{self.bvid}_p{self.page}"


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
        videos: 解析得到的分P 视频列表。
    """

    series_id: str
    title: str
    cover_url: str
    source_url: str
    videos: list[LinkedVideo] = field(default_factory=list)
