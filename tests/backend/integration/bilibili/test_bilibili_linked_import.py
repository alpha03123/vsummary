from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path


from backend.bilibili.ytdlp_bilibili import YtDlpBilibiliResolver
from backend.video_summary.infrastructure.storage.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.library.constants import PLAYGROUND_SERIES_ID
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.models import BilibiliUrlInfoDTO
from backend.video_summary.library.usecases.linked_videos import ResolveBilibiliVideo


class YtDlpBilibiliResolverTests(unittest.TestCase):
    def test_resolve_single_video_extracts_linked_video_metadata(self) -> None:
        resolver = YtDlpBilibiliResolver(
            extractor=lambda url: {
                "id": "BV1xx411c7mD",
                "title": "公开课第一讲",
                "duration": 123,
                "thumbnail": "https://example.test/cover.jpg",
                "webpage_url": url,
            },
        )

        result = asyncio.run(
            resolver.resolve_single_video(
                BilibiliUrlInfoDTO(url="https://www.bilibili.com/video/BV1xx411c7mD")
            )
        )

        self.assertEqual(result.video_id, "BV1xx411c7mD")
        self.assertEqual(result.title, "公开课第一讲")
        self.assertEqual(result.duration_seconds, 123)
        self.assertEqual(result.source_url, "https://www.bilibili.com/video/BV1xx411c7mD")

    def test_resolve_series_maps_playlist_entries_to_linked_series(self) -> None:
        resolver = YtDlpBilibiliResolver(
            extractor=lambda url: {
                "id": "playlist-1",
                "title": "课程合集",
                "thumbnail": "https://example.test/series.jpg",
                "webpage_url": url,
                "entries": [
                    {
                        "id": "BV1xx411c7mD",
                        "title": "第一讲",
                        "duration": 123,
                        "thumbnail": "https://example.test/1.jpg",
                        "webpage_url": "https://www.bilibili.com/video/BV1xx411c7mD",
                    },
                    {
                        "id": "BV1yy411c7mE",
                        "title": "第二讲",
                        "duration": 456,
                        "thumbnail": "https://example.test/2.jpg",
                        "webpage_url": "https://www.bilibili.com/video/BV1yy411c7mE",
                    },
                ],
            },
        )

        result = asyncio.run(
            resolver.resolve_series(
                BilibiliUrlInfoDTO(url="https://space.bilibili.com/1/lists/2?type=season")
            )
        )

        self.assertEqual(result.series_id, "bilibili-playlist-1")
        self.assertEqual(result.title, "课程合集")
        self.assertEqual([video.video_id for video in result.videos], ["BV1xx411c7mD", "BV1yy411c7mE"])

    def test_resolve_series_uses_bilibili_view_titles_when_entries_only_have_bvids(self) -> None:
        resolver = YtDlpBilibiliResolver(
            extractor=lambda url: {
                "id": "playlist-1",
                "title": "BV1xx411c7mD",
                "thumbnail": "",
                "webpage_url": url,
                "entries": [
                    {
                        "id": "BV1xx411c7mD",
                        "title": "BV1xx411c7mD",
                        "duration": 123,
                        "webpage_url": "https://www.bilibili.com/video/BV1xx411c7mD",
                    },
                    {
                        "id": "BV1yy411c7mE",
                        "title": "BV1yy411c7mE",
                        "duration": 456,
                        "webpage_url": "https://www.bilibili.com/video/BV1yy411c7mE",
                    },
                ],
            },
            view_extractor=lambda bvid: {
                "title": "课程合集",
                "ugc_season": {
                    "title": "课程合集",
                    "sections": [
                        {
                            "episodes": [
                                {"bvid": "BV1xx411c7mD", "title": "第一讲"},
                                {"bvid": "BV1yy411c7mE", "title": "第二讲"},
                            ]
                        }
                    ],
                },
            },
        )

        result = asyncio.run(
            resolver.resolve_series(
                BilibiliUrlInfoDTO(url="https://space.bilibili.com/1/lists/2?type=season")
            )
        )

        self.assertEqual(result.title, "课程合集")
        self.assertEqual([video.title for video in result.videos], ["第一讲", "第二讲"])

    def test_resolve_series_uses_page_parts_when_entries_are_single_bvid_pages(self) -> None:
        resolver = YtDlpBilibiliResolver(
            extractor=lambda url: {
                "id": "BV1xx411c7mD",
                "title": "BV1xx411c7mD",
                "webpage_url": url,
                "entries": [
                    {
                        "id": "BV1xx411c7mD",
                        "title": "BV1xx411c7mD",
                        "page_number": 1,
                        "webpage_url": "https://www.bilibili.com/video/BV1xx411c7mD",
                    },
                    {
                        "id": "BV1xx411c7mD",
                        "title": "BV1xx411c7mD",
                        "page_number": 2,
                        "webpage_url": "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
                    },
                ],
            },
            view_extractor=lambda bvid: {
                "title": "多 P 课程",
                "pages": [
                    {"page": 1, "part": "第一 P"},
                    {"page": 2, "part": "第二 P"},
                ],
            },
        )

        result = asyncio.run(
            resolver.resolve_series(
                BilibiliUrlInfoDTO(url="https://www.bilibili.com/video/BV1xx411c7mD")
            )
        )

        self.assertEqual(result.title, "多 P 课程")
        self.assertEqual([video.video_id for video in result.videos], ["BV1xx411c7mD", "BV1xx411c7mD_p2"])
        self.assertEqual([video.title for video in result.videos], ["第一 P", "第二 P"])

    def test_resolve_series_uses_page_parts_when_flat_entries_only_have_page_urls(self) -> None:
        resolver = YtDlpBilibiliResolver(
            extractor=lambda url: {
                "id": "BV1xx411c7mD",
                "title": "多 P 课程",
                "webpage_url": url,
                "entries": [
                    {"url": "https://www.bilibili.com/video/BV1xx411c7mD?p=1"},
                    {"url": "https://www.bilibili.com/video/BV1xx411c7mD?p=2"},
                ],
            },
            view_extractor=lambda bvid: {
                "title": "多 P 课程",
                "pages": [
                    {"page": 1, "part": "第一 P"},
                    {"page": 2, "part": "第二 P"},
                ],
            },
        )

        result = asyncio.run(
            resolver.resolve_series(
                BilibiliUrlInfoDTO(url="https://www.bilibili.com/video/BV1xx411c7mD")
            )
        )

        self.assertEqual([video.video_id for video in result.videos], ["BV1xx411c7mD", "BV1xx411c7mD_p2"])
        self.assertEqual([video.title for video in result.videos], ["第一 P", "第二 P"])


class FileSystemLinkedSeriesTests(unittest.TestCase):
    def test_list_series_reports_linked_video_until_downloaded_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = FileSystemVideoWorkspace(Path(tmp))
            workspace.save_linked_series(
                LinkedSeries(
                    series_id="bilibili-playlist-1",
                    title="课程合集",
                    cover_url="",
                    source_url="https://example.test/series",
                    videos=[
                        LinkedVideo(
                            bvid="BV1xx411c7mD",
                            page=1,
                            title="第一讲",
                            cover_url="",
                            duration_seconds=123,
                            source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                        )
                    ],
                )
            )

            linked_series = _find_series(workspace.list_series(), "bilibili-playlist-1")
            linked_video = linked_series.videos[0]
            self.assertTrue(linked_series.is_linked)
            self.assertTrue(linked_video.is_linked)
            self.assertEqual(linked_video.status, "linked")

            video_dir = Path(tmp) / "videos" / "bilibili-playlist-1"
            video_dir.mkdir(parents=True)
            (video_dir / "BV1xx411c7mD.mp4").write_bytes(b"fake video")

            downloaded_series = _find_series(workspace.list_series(), "bilibili-playlist-1")
            downloaded_video = downloaded_series.videos[0]
            self.assertFalse(downloaded_video.is_linked)
            self.assertEqual(downloaded_video.status, "pending")

    def test_delete_video_removes_linked_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = FileSystemVideoWorkspace(Path(tmp))
            workspace.save_linked_series(
                LinkedSeries(
                    series_id=PLAYGROUND_SERIES_ID,
                    title="Playground",
                    cover_url="",
                    source_url="",
                    videos=[
                        LinkedVideo(
                            bvid="BV1xx411c7mD",
                            page=1,
                            title="第一讲",
                            cover_url="",
                            duration_seconds=123,
                            source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                        )
                    ],
                )
            )

            self.assertTrue(workspace.delete_video(PLAYGROUND_SERIES_ID, "BV1xx411c7mD"))

            linked_series = workspace.get_linked_series(PLAYGROUND_SERIES_ID)
            self.assertIsNotNone(linked_series)
            self.assertEqual(linked_series.videos, [])


class ResolveBilibiliVideoTests(unittest.TestCase):
    def test_resolve_video_adds_unique_linked_video_to_playground(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = FileSystemVideoWorkspace(Path(tmp))
            resolver = _FakeResolver(
                LinkedVideo(
                    bvid="BV1xx411c7mD",
                    page=1,
                    title="第一讲",
                    cover_url="",
                    duration_seconds=123,
                    source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                )
            )
            usecase = ResolveBilibiliVideo(workspace, resolver, _NoopInvalidator())

            first = asyncio.run(usecase.run(url="https://www.bilibili.com/video/BV1xx411c7mD"))
            second = asyncio.run(usecase.run(url="https://www.bilibili.com/video/BV1xx411c7mD"))

            self.assertEqual(first.id, "BV1xx411c7mD")
            self.assertEqual(second.id, "BV1xx411c7mD")
            linked_series = workspace.get_linked_series(PLAYGROUND_SERIES_ID)
            self.assertIsNotNone(linked_series)
            self.assertEqual(len(linked_series.videos), 1)

    def test_resolve_video_invalidates_workspace_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = FileSystemVideoWorkspace(Path(tmp))
            resolver = _FakeResolver(
                LinkedVideo(
                    bvid="BV1xx411c7mD",
                    page=1,
                    title="第一讲",
                    cover_url="",
                    duration_seconds=123,
                    source_url="https://www.bilibili.com/video/BV1xx411c7mD",
                )
            )
            invalidator = _RecordingInvalidator()
            usecase = ResolveBilibiliVideo(workspace, resolver, invalidator)

            asyncio.run(usecase.run(url="https://www.bilibili.com/video/BV1xx411c7mD"))

            self.assertEqual(invalidator.calls, 1)


def _find_series(series, series_id: str):
    return next(item for item in series if item.id == series_id)


class _FakeResolver:
    def __init__(self, video: LinkedVideo) -> None:
        self._video = video

    async def resolve_series(self, url_info: BilibiliUrlInfoDTO) -> LinkedSeries:
        raise NotImplementedError

    async def resolve_single_video(self, url_info: BilibiliUrlInfoDTO) -> LinkedVideo:
        return self._video


class _NoopInvalidator:
    def invalidate(self) -> None:
        pass


class _RecordingInvalidator:
    def __init__(self) -> None:
        self.calls = 0

    def invalidate(self) -> None:
        self.calls += 1


if __name__ == "__main__":
    unittest.main()
