from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BilibiliPluginVideoKey:
    bvid: str
    page: int = 1

    @property
    def page_dir_name(self) -> str:
        return f"p{self.page}"

    @property
    def video_id(self) -> str:
        return self.bvid if self.page == 1 else f"{self.bvid}_p{self.page}"

    @property
    def task_id(self) -> str:
        return f"plugin/bilibili/{self.bvid}/{self.page_dir_name}"


@dataclass(frozen=True)
class BilibiliPluginVideoMeta:
    bvid: str
    page: int
    video_id: str
    title: str
    source_url: str
    cover_url: str
    duration_seconds: int


@dataclass(frozen=True)
class BilibiliPluginSummaryResult:
    key: BilibiliPluginVideoKey
    meta: BilibiliPluginVideoMeta
    summary: dict[str, object]
