from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.video_summary.library.linked_models import LinkedVideo
from backend.video_summary.library.models import LibrarySeriesDTO
from backend.video_summary.library.usecases.linked_videos import ResolveBilibiliVideo, ResolveLinkedVideo


class _Resolver:
    async def resolve_single_video(self, _url):
        return LinkedVideo(
            source_id="BV1example",
            item_index=1,
            title="Example",
            cover_url="",
            duration_seconds=60,
            source_url="https://www.bilibili.com/video/BV1example",
        )


class _Workspace:
    def __init__(self, series):
        self.series = series
        self.saved = None

    def ensure_playground_series(self):
        existing = next((item for item in self.series if item.kind == "playground"), None)
        if existing is None:
            existing = LibrarySeriesDTO(id="created-playground", title="Playground", videos=[], kind="playground")
            self.series.append(existing)
        return existing.id

    def ensure_bilibili_inbox_series(self):
        existing = next((item for item in self.series if item.kind == "bilibili_inbox"), None)
        if existing is None:
            existing = LibrarySeriesDTO(id="bilibili-inbox", title="B站导入", videos=[], kind="bilibili_inbox")
            self.series.append(existing)
        return existing.id

    def list_series(self):
        return self.series

    def get_linked_series(self, _series_id):
        return None

    def save_linked_series(self, series):
        self.saved = series


class _Invalidator:
    def invalidate(self):
        pass


class ResolveLinkedVideoPlaygroundTests(unittest.IsolatedAsyncioTestCase):
    async def test_bilibili_route_creates_playground_series_for_first_video(self):
        workspace = _Workspace([])

        await ResolveBilibiliVideo(
            workspace,
            _Resolver(),
            _Invalidator(),
            parser=SimpleNamespace(parse=lambda url: url),
        ).run(url="https://www.bilibili.com/video/BV1example")

        self.assertEqual(workspace.saved.series_id, "created-playground")
        self.assertEqual(workspace.saved.title, "Playground")

    async def test_bilibili_plugin_route_creates_its_dedicated_inbox(self):
        workspace = _Workspace([])

        await ResolveBilibiliVideo(
            workspace,
            _Resolver(),
            _Invalidator(),
            parser=SimpleNamespace(parse=lambda url: url),
        ).run_inbox(url="https://www.bilibili.com/video/BV1example")

        self.assertEqual(workspace.saved.series_id, "bilibili-inbox")
        self.assertEqual(workspace.saved.title, "B站导入")

    async def test_first_external_video_creates_playground_series(self):
        workspace = _Workspace([])

        await ResolveLinkedVideo(workspace, {"bilibili": _Resolver()}, _Invalidator()).run(
            provider="bilibili",
            url="https://www.bilibili.com/video/BV1example",
        )

        self.assertEqual(workspace.saved.series_id, "created-playground")
        self.assertEqual(workspace.saved.title, "Playground")
        self.assertEqual(len(workspace.saved.videos), 1)

    async def test_external_video_reuses_existing_playground_series(self):
        workspace = _Workspace([
            LibrarySeriesDTO(id="existing-playground", title="Playground", videos=[], kind="playground"),
        ])

        await ResolveLinkedVideo(workspace, {"bilibili": _Resolver()}, _Invalidator()).run(
            provider="bilibili",
            url="https://www.bilibili.com/video/BV1example",
        )

        self.assertEqual(workspace.saved.series_id, "existing-playground")


if __name__ == "__main__":
    unittest.main()
