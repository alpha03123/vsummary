"""Agent-managed linked series use cases."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
from urllib.parse import urlparse

from backend.video_summary.library.linked_models import LinkedSeries
from backend.video_summary.library.models import LibrarySeriesDTO, LibraryVideoCardDTO
from backend.video_summary.library.parsers import DefaultBilibiliUrlParser
from backend.video_summary.library.ports import (
    BilibiliUrlParser,
    LinkedSeriesResolverWorkspace,
    LinkedVideoResolver,
    WorkspaceIndexInvalidator,
)
from backend.video_summary.library.usecases.linked_videos import _to_series_dto, _to_video_card_dto


@dataclass(frozen=True)
class AgentVideoCandidate:
    url: str
    title: str = ""
    source: str = "bilibili"


class CreateAgentSeries:
    def __init__(self, workspace: LinkedSeriesResolverWorkspace, invalidator: WorkspaceIndexInvalidator) -> None:
        self._workspace = workspace
        self._invalidator = invalidator

    def run(self, *, title: str, source: str = "agent", notes: str = "") -> LibrarySeriesDTO:
        del notes
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("title cannot be blank")
        normalized_source = source.strip() or "agent"
        series_id = f"agent-{_slugify(normalized_title)}"
        existing = self._workspace.get_linked_series(series_id)
        if existing is not None:
            if existing.title == normalized_title:
                return _to_series_dto(existing)
            series_id = self._unique_series_id(series_id, normalized_title)
        series = LinkedSeries(
            series_id=series_id,
            title=normalized_title,
            cover_url="",
            source_url=f"agent://{normalized_source}",
            videos=[],
        )
        self._workspace.save_linked_series(series)
        self._invalidator.invalidate()
        return _to_series_dto(series)

    def _unique_series_id(self, base_id: str, title: str) -> str:
        suffix = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
        candidate = f"{base_id}-{suffix}"
        if self._workspace.get_linked_series(candidate) is None:
            return candidate
        index = 2
        while self._workspace.get_linked_series(f"{candidate}-{index}") is not None:
            index += 1
        return f"{candidate}-{index}"


class AddAgentSeriesVideos:
    def __init__(
        self,
        workspace: LinkedSeriesResolverWorkspace,
        resolver: LinkedVideoResolver,
        invalidator: WorkspaceIndexInvalidator,
        parser: BilibiliUrlParser | None = None,
    ) -> None:
        self._workspace = workspace
        self._resolver = resolver
        self._invalidator = invalidator
        self._parser = parser or DefaultBilibiliUrlParser()

    async def run(self, *, series_id: str, videos: list[AgentVideoCandidate]) -> list[LibraryVideoCardDTO]:
        if not videos:
            raise ValueError("videos cannot be empty")
        linked_series = self._workspace.get_linked_series(series_id)
        if linked_series is None:
            raise LookupError(f"linked series not found: {series_id}")

        resolved_videos = []
        seen_urls: set[str] = set()
        for candidate in videos:
            normalized_url = candidate.url.strip()
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            if candidate.source != "bilibili":
                raise ValueError(f"unsupported video source: {candidate.source}")
            scheme = urlparse(normalized_url).scheme.lower()
            if scheme not in {"http", "https"}:
                raise ValueError("video URL must use http or https")
            parsed_url = urlparse(normalized_url)
            host = (parsed_url.hostname or "").lower()
            if host not in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"}:
                raise ValueError("video URL must be a supported Bilibili host")
            resolved_video = await self._resolver.resolve_single_video(self._parser.parse(normalized_url))
            candidate_title = candidate.title.strip()
            if candidate_title:
                resolved_video = replace(resolved_video, title=candidate_title)
            resolved_videos.append(resolved_video)

        selected_video_ids = {video.video_id for video in linked_series.videos}
        videos_to_append = []
        for video in resolved_videos:
            if video.video_id in selected_video_ids:
                continue
            selected_video_ids.add(video.video_id)
            videos_to_append.append(video)
        if videos_to_append:
            self._workspace.save_linked_series(
                LinkedSeries(
                    series_id=linked_series.series_id,
                    title=linked_series.title,
                    cover_url=linked_series.cover_url,
                    source_url=linked_series.source_url,
                    videos=[*linked_series.videos, *videos_to_append],
                )
            )
            self._invalidator.invalidate()
        return [_to_video_card_dto(video) for video in resolved_videos]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "series"
