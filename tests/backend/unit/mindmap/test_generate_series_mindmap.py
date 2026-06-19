from __future__ import annotations

import asyncio
import unittest

from backend.video_summary.library.models import (
    LibrarySeriesDTO,
    LibraryVideoCardDTO,
    VideoSummaryDTO,
    WorkspaceDTO,
)


class FakeSeriesWorkspace:
    def __init__(self, series_list=None, summaries_by_video=None, catalog=None, mindmap=None):
        self._series_list = series_list or []
        self._summaries_by_video = summaries_by_video or {}
        self._catalog = catalog
        self._mindmap = mindmap

    def list_series(self):
        return self._series_list

    def get_workspace(self):
        return WorkspaceDTO(id="ws", title="ws")

    def get_video_summary(self, series_id, video_id):
        return self._summaries_by_video.get(video_id)

    def get_series_catalog(self, series_id):
        return self._catalog

    def get_series_mindmap(self, series_id):
        return self._mindmap

    def get_series_dir(self, series_id):
        from pathlib import Path
        return Path("/tmp/fake")


class FakeSeriesMindmapGenerator:
    def __init__(self):
        self.last_call = None

    async def run(self, *, series_id, series_title, catalog, video_summaries, progress_reporter=None):
        self.last_call = {
            "series_id": series_id,
            "catalog": catalog,
            "video_summaries": video_summaries,
            "progress_reporter": progress_reporter,
        }


class GenerateSeriesMindmapFromLibraryTests(unittest.TestCase):
    def test_collects_all_video_summaries(self):
        from backend.video_summary.library.usecases.series_mindmap_generation import GenerateSeriesMindmapFromLibrary

        workspace = FakeSeriesWorkspace(
            series_list=[LibrarySeriesDTO(id="s1", title="S1", videos=[
                LibraryVideoCardDTO(id="v1", title="V1", source_name="v1", processed=True, status="ready"),
                LibraryVideoCardDTO(id="v2", title="V2", source_name="v2", processed=True, status="ready"),
            ])],
            summaries_by_video={
                "v1": VideoSummaryDTO(series_id="s1", video_id="v1", title="V1", summary={"chapters": []}),
                "v2": VideoSummaryDTO(series_id="s1", video_id="v2", title="V2", summary={"chapters": []}),
            },
        )
        generator = FakeSeriesMindmapGenerator()
        use_case = GenerateSeriesMindmapFromLibrary(workspace, generator)
        asyncio.run(use_case.run("s1"))
        self.assertEqual(len(generator.last_call["video_summaries"]), 2)

    def test_skips_videos_without_summary(self):
        from backend.video_summary.library.usecases.series_mindmap_generation import GenerateSeriesMindmapFromLibrary

        workspace = FakeSeriesWorkspace(
            series_list=[LibrarySeriesDTO(id="s1", title="S1", videos=[
                LibraryVideoCardDTO(id="v1", title="V1", source_name="v1", processed=True, status="ready"),
                LibraryVideoCardDTO(id="v2", title="V2", source_name="v2", processed=False, status="pending"),
            ])],
            summaries_by_video={
                "v1": VideoSummaryDTO(series_id="s1", video_id="v1", title="V1", summary={"chapters": []}),
            },
        )
        generator = FakeSeriesMindmapGenerator()
        use_case = GenerateSeriesMindmapFromLibrary(workspace, generator)
        asyncio.run(use_case.run("s1"))
        self.assertEqual(len(generator.last_call["video_summaries"]), 1)

    def test_returns_none_when_no_summaries(self):
        from backend.video_summary.library.usecases.series_mindmap_generation import GenerateSeriesMindmapFromLibrary

        workspace = FakeSeriesWorkspace(
            series_list=[LibrarySeriesDTO(id="s1", title="S1", videos=[
                LibraryVideoCardDTO(id="v1", title="V1", source_name="v1", processed=False, status="pending"),
            ])],
            summaries_by_video={},
        )
        generator = FakeSeriesMindmapGenerator()
        use_case = GenerateSeriesMindmapFromLibrary(workspace, generator)
        result = asyncio.run(use_case.run("s1"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
