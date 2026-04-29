from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LinkedVideo:
    bvid: str
    page: int
    title: str
    cover_url: str
    duration_seconds: int
    source_url: str

    @property
    def video_id(self) -> str:
        return self.bvid if self.page == 1 else f"{self.bvid}_p{self.page}"


@dataclass(frozen=True)
class LinkedSeries:
    series_id: str
    title: str
    cover_url: str
    source_url: str
    videos: list[LinkedVideo] = field(default_factory=list)
