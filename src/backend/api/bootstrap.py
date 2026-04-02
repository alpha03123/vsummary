from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.video_summary.infrastructure.sample_catalog import SampleSummaryCatalog
from backend.video_summary.library.usecases.browse_library import GetVideoSummary, ListVideoLibrary


@dataclass(frozen=True)
class ApiContainer:
    list_video_library: ListVideoLibrary
    get_video_summary: GetVideoSummary


def build_api_container(root_dir: Path) -> ApiContainer:
    catalog = SampleSummaryCatalog(root_dir)
    return ApiContainer(
        list_video_library=ListVideoLibrary(catalog),
        get_video_summary=GetVideoSummary(catalog),
    )
