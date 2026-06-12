from __future__ import annotations

from typing import Protocol

from backend.video_summary.workspace.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.workspace.models import BilibiliUrlInfoDTO


class LinkedVideoResolver(Protocol):
    async def resolve_series(self, url_info: BilibiliUrlInfoDTO) -> LinkedSeries:
        ...

    async def resolve_single_video(self, url_info: BilibiliUrlInfoDTO) -> LinkedVideo:
        ...


class BilibiliUrlParser(Protocol):
    def parse(self, url: str) -> BilibiliUrlInfoDTO:
        ...


class LinkedVideoDownloadStarter(Protocol):
    def start(self, *, series_id: str, video: LinkedVideo) -> str:
        ...