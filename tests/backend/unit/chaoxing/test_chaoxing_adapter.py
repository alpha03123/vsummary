from __future__ import annotations

import tempfile
import unittest
import json
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread

from backend.chaoxing.chaoxing_api import (
    CHAOXING_ANTISPIDER_MESSAGE,
    CHAOXING_REINIT_REQUIRED_MESSAGE,
    ChaoxingChapterRecord,
    ChaoxingCourseImporter,
    ChaoxingCourseRecord,
    ChaoxingDownloaderClient,
    ChaoxingImportCancelled,
    ChaoxingLinkedVideoDownloadStarter,
    ChaoxingVideoRecord,
)
from backend.video_summary.infrastructure.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.library.linked_models import LinkedVideo


@dataclass(frozen=True)
class _Course:
    course_key: str
    title: str
    teacher: str = "老师"
    open_time: str = ""


@dataclass(frozen=True)
class _Chapter:
    chapter_key: str
    title: str
    order: str = "1"


@dataclass(frozen=True)
class _Video:
    video_key: str
    chapter_key: str
    title: str
    duration: int = 0
    filename: str = ""


class ChaoxingCourseImporterTests(unittest.TestCase):
    def test_import_course_maps_all_videos_to_linked_series(self) -> None:
        client = _FakeClient(
            courses=[_Course(course_key="course-1", title="线性代数")],
            chapters=[_Chapter(chapter_key="chapter-1", title="第一章", order="1")],
            videos=[_Video(video_key="video:1", chapter_key="chapter-1", title="第一讲", duration=123)],
        )
        importer = ChaoxingCourseImporter(client=client)

        series = importer.import_course("course-1")

        self.assertEqual(series.series_id, "chaoxing-course-1")
        self.assertEqual(series.title, "线性代数")
        self.assertEqual(len(series.videos), 1)
        self.assertEqual(series.videos[0].provider, "chaoxing")
        self.assertEqual(series.videos[0].download_key, "video:1")
        self.assertEqual(series.videos[0].video_id, "chaoxing-video-1")

    def test_import_course_reports_chapter_loading_stage(self) -> None:
        importer = ChaoxingCourseImporter(
            client=_FailingStageClient(
                courses=[_Course(course_key="course-1", title="线性代数")],
                chapter_error=RuntimeError("触发超星访问验证"),
            )
        )

        with self.assertRaisesRegex(RuntimeError, "读取超星课程章节失败：线性代数；触发超星访问验证"):
            importer.import_course("course-1")

    def test_import_course_reports_video_loading_stage(self) -> None:
        importer = ChaoxingCourseImporter(
            client=_FailingStageClient(
                courses=[_Course(course_key="course-1", title="线性代数")],
                chapters=[_Chapter(chapter_key="chapter-1", title="第一章")],
                video_error=RuntimeError("触发超星访问验证"),
            )
        )

        with self.assertRaisesRegex(RuntimeError, "读取超星章节视频失败：第一章；触发超星访问验证"):
            importer.import_course("course-1")

    def test_import_course_skips_unsupported_non_video_chapters(self) -> None:
        client = _MixedChapterClient()
        importer = ChaoxingCourseImporter(client=client)

        series = importer.import_course("course-1")

        self.assertEqual(len(series.videos), 1)
        self.assertEqual(series.videos[0].download_key, "video-1")

    def test_import_course_skips_legacy_empty_chapter_parse_error(self) -> None:
        client = _MixedChapterClient(unsupported_error=RuntimeError("未解析到课程章节，学习通页面结构可能已变化"))
        importer = ChaoxingCourseImporter(client=client)

        series = importer.import_course("course-1")

        self.assertEqual(len(series.videos), 1)
        self.assertEqual(series.videos[0].download_key, "video-1")

    def test_import_course_stops_between_chapters_when_cancel_requested(self) -> None:
        tracker = InMemoryProgressTracker()
        task_id = "chaoxing-import-1"
        reporter = tracker.create_reporter(task_id)
        client = _CancelAfterFirstChapterClient(tracker=tracker, task_id=task_id)
        importer = ChaoxingCourseImporter(client=client)

        with self.assertRaisesRegex(ChaoxingImportCancelled, "超星课程导入已取消"):
            importer.import_course("course-1", progress=reporter)

        self.assertEqual(client.video_calls, ["chapter-1"])

    def test_import_course_cancel_wins_over_late_video_error(self) -> None:
        tracker = InMemoryProgressTracker()
        task_id = "chaoxing-import-1"
        reporter = tracker.create_reporter(task_id)
        client = _CancelThenFailVideoClient(tracker=tracker, task_id=task_id)
        importer = ChaoxingCourseImporter(client=client)

        with self.assertRaisesRegex(ChaoxingImportCancelled, "超星课程导入已取消"):
            importer.import_course("course-1", progress=reporter)

    def test_list_videos_waits_for_running_import(self) -> None:
        client = _BlockingImportClient()
        importer = ChaoxingCourseImporter(client=client)

        import_thread = Thread(target=lambda: importer.import_course("course-1"), daemon=True)
        import_thread.start()
        self.assertTrue(client.import_entered.wait(timeout=1.0))

        list_thread = Thread(target=lambda: importer.list_videos("chapter-2"), daemon=True)
        list_thread.start()

        self.assertFalse(client.list_entered.wait(timeout=0.1))
        client.release_import.set()
        import_thread.join(timeout=1.0)
        list_thread.join(timeout=1.0)

        self.assertFalse(import_thread.is_alive())
        self.assertFalse(list_thread.is_alive())
        self.assertTrue(client.list_entered.is_set())


class ChaoxingDownloaderClientTests(unittest.TestCase):
    def test_requires_chromium_before_init(self) -> None:
        client = ChaoxingDownloaderClient(
            state_dir=Path("state"),
            chromium_downloaded=lambda: False,
            downloader_cls=_UnusedDownloader,
        )

        with self.assertRaisesRegex(RuntimeError, "Chromium"):
            client.init()

    def test_is_initialized_delegates_to_downloader(self) -> None:
        client = ChaoxingDownloaderClient(
            state_dir=Path("state"),
            chromium_downloaded=lambda: True,
            downloader_cls=_InitializedDownloader,
        )

        self.assertTrue(client.is_initialized())

    def test_init_passes_cancel_check_to_downloader(self) -> None:
        _RecordingInitDownloader.cancel_check = None
        _RecordingInitDownloader.request_delay = None
        _RecordingInitDownloader.course_delay = None
        client = ChaoxingDownloaderClient(
            state_dir=Path("state"),
            chromium_downloaded=lambda: True,
            downloader_cls=_RecordingInitDownloader,
        )

        client.init()
        client.cancel_init()

        self.assertIsNotNone(_RecordingInitDownloader.cancel_check)
        self.assertTrue(_RecordingInitDownloader.cancel_check())
        self.assertEqual(_RecordingInitDownloader.request_delay, 0.2)
        self.assertEqual(_RecordingInitDownloader.course_delay, 0.3)

    def test_antispider_response_is_reported_as_clear_runtime_error(self) -> None:
        client = ChaoxingDownloaderClient(
            state_dir=Path("state"),
            chromium_downloaded=lambda: True,
            downloader_cls=_AntispiderDownloader,
        )

        with self.assertRaisesRegex(RuntimeError, CHAOXING_ANTISPIDER_MESSAGE):
            client.list_courses()

    def test_same_target_antispider_three_times_clears_state_and_requires_reinit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "session.json").write_text("{}", encoding="utf-8")
            (state_dir / "cache.json").write_text("{}", encoding="utf-8")
            client = ChaoxingDownloaderClient(
                state_dir=state_dir,
                chromium_downloaded=lambda: True,
                downloader_cls=_AntispiderDownloader,
            )

            with self.assertRaisesRegex(RuntimeError, CHAOXING_ANTISPIDER_MESSAGE):
                client.list_videos("chapter-1")
            with self.assertRaisesRegex(RuntimeError, CHAOXING_ANTISPIDER_MESSAGE):
                client.list_videos("chapter-1")
            with self.assertRaisesRegex(RuntimeError, CHAOXING_REINIT_REQUIRED_MESSAGE):
                client.list_videos("chapter-1")

            self.assertFalse(state_dir.exists())

    def test_list_courses_uses_initialized_cache_before_downloader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "cache.json").write_text(
                json.dumps(
                    {
                        "courses": [
                            {
                                "course_key": "course-1",
                                "title": "缓存课程",
                                "teacher": "老师",
                                "open_time": "开课时间",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            client = ChaoxingDownloaderClient(
                state_dir=state_dir,
                chromium_downloaded=lambda: True,
                downloader_cls=_NetworkShouldNotBeCalledDownloader,
            )

            courses = client.list_courses()

            self.assertEqual(courses, [ChaoxingCourseRecord("course-1", "缓存课程", "老师", "开课时间")])

    def test_list_courses_reports_invalid_cache_instead_of_falling_back_to_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "cache.json").write_text(json.dumps({"courses": {}}), encoding="utf-8")
            client = ChaoxingDownloaderClient(
                state_dir=state_dir,
                chromium_downloaded=lambda: True,
                downloader_cls=_NetworkShouldNotBeCalledDownloader,
            )

            with self.assertRaisesRegex(RuntimeError, "课程缓存格式错误"):
                client.list_courses()

    def test_list_chapters_uses_cache_before_downloader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "cache.json").write_text(
                json.dumps(
                    {
                        "chapters": [
                            {
                                "course_key": "course-1",
                                "chapter_key": "chapter-1",
                                "title": "缓存章节",
                                "order": "1.1",
                            },
                            {
                                "course_key": "course-2",
                                "chapter_key": "chapter-2",
                                "title": "其他章节",
                                "order": "2.1",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            client = ChaoxingDownloaderClient(
                state_dir=state_dir,
                chromium_downloaded=lambda: True,
                downloader_cls=_NetworkShouldNotBeCalledDownloader,
            )

            chapters = client.list_chapters("course-1")

            self.assertEqual(chapters, [ChaoxingChapterRecord(chapter_key="chapter-1", title="缓存章节", order="1.1")])

    def test_list_videos_uses_cache_before_downloader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "cache.json").write_text(
                json.dumps(
                    {
                        "videos": [
                            {
                                "chapter_key": "chapter-1",
                                "video_key": "video-1",
                                "title": "缓存视频",
                                "duration": 12,
                                "filename": "缓存视频.mp4",
                            },
                            {
                                "chapter_key": "chapter-2",
                                "video_key": "video-2",
                                "title": "其他视频",
                                "duration": 8,
                                "filename": "其他视频.mp4",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            client = ChaoxingDownloaderClient(
                state_dir=state_dir,
                chromium_downloaded=lambda: True,
                downloader_cls=_NetworkShouldNotBeCalledDownloader,
            )

            videos = client.list_videos("chapter-1")

            self.assertEqual(
                videos,
                [
                    ChaoxingVideoRecord(
                        video_key="video-1",
                        chapter_key="chapter-1",
                        title="缓存视频",
                        duration=12,
                        filename="缓存视频.mp4",
                    )
                ],
            )

    def test_import_course_uses_cached_course_videos_when_chapter_mapping_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "cache.json").write_text(
                json.dumps(
                    {
                        "courses": [
                            {
                                "course_key": "course-1",
                                "title": "离散数学",
                                "teacher": "老师",
                                "open_time": "",
                            }
                        ],
                        "chapters": [
                            {
                                "course_key": "course-1",
                                "chapter_key": "chapter-1",
                                "title": "第一章",
                                "order": "1",
                            }
                        ],
                        "videos": [
                            {
                                "course_key": "course-1",
                                "video_key": "video-1",
                                "title": "命题逻辑",
                                "duration": 123,
                                "filename": "命题逻辑.mp4",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            client = ChaoxingDownloaderClient(
                state_dir=state_dir,
                chromium_downloaded=lambda: True,
                downloader_cls=_NetworkShouldNotBeCalledDownloader,
            )
            importer = ChaoxingCourseImporter(client=client)

            series = importer.import_course("course-1")

            self.assertEqual(series.title, "离散数学")
            self.assertEqual(len(series.videos), 1)
            self.assertEqual(series.videos[0].download_key, "video-1")


class ChaoxingLinkedVideoDownloadStarterTests(unittest.TestCase):
    def test_downloads_with_video_id_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            downloader = _RecordingDownloadClient()
            starter = ChaoxingLinkedVideoDownloadStarter(
                root_dir=Path(tmp),
                client=downloader,
                progress_tracker=InMemoryProgressTracker(),
                run_in_background=False,
            )
            video = LinkedVideo(
                bvid="chaoxing-video-1",
                page=1,
                title="第一讲",
                cover_url="",
                duration_seconds=0,
                source_url="chaoxing://video/video-1",
                provider="chaoxing",
                download_key="video-1",
            )

            task_id = starter.start(series_id="chaoxing-course-1", video=video)

            self.assertEqual(task_id, "download/chaoxing-course-1/chaoxing-video-1")
            self.assertEqual(downloader.calls[0]["video_key"], "video-1")
            self.assertEqual(downloader.calls[0]["filename"], "chaoxing-video-1.mp4")
            self.assertEqual(downloader.calls[0]["output_dir"], Path(tmp) / "videos" / "chaoxing-course-1")

    def test_cancelled_download_reports_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tracker = InMemoryProgressTracker()
            downloader = _CancellingDownloadClient(tracker)
            starter = ChaoxingLinkedVideoDownloadStarter(
                root_dir=Path(tmp),
                client=downloader,
                progress_tracker=tracker,
                run_in_background=False,
            )
            video = LinkedVideo(
                bvid="chaoxing-video-1",
                page=1,
                title="第一讲",
                cover_url="",
                duration_seconds=0,
                source_url="chaoxing://video/video-1",
                provider="chaoxing",
                download_key="video-1",
            )

            task_id = starter.start(series_id="chaoxing-course-1", video=video)

            snapshot = tracker.get_snapshot(task_id)
            self.assertEqual(snapshot.status, "cancelled")
            self.assertEqual(snapshot.detail, "下载已取消")


class _FakeClient:
    def __init__(self, *, courses, chapters, videos) -> None:
        self._courses = courses
        self._chapters = chapters
        self._videos = videos

    def list_courses(self):
        return self._courses

    def list_chapters(self, course_key: str):
        del course_key
        return self._chapters

    def list_videos(self, chapter_key: str):
        return [video for video in self._videos if video.chapter_key == chapter_key]

    def list_cached_course_videos(self, course_key: str):
        del course_key
        return []


class _FailingStageClient:
    def __init__(self, *, courses, chapters=None, chapter_error=None, video_error=None) -> None:
        self._courses = courses
        self._chapters = chapters or []
        self._chapter_error = chapter_error
        self._video_error = video_error

    def list_courses(self):
        return self._courses

    def list_chapters(self, course_key: str):
        del course_key
        if self._chapter_error:
            raise self._chapter_error
        return self._chapters

    def list_videos(self, chapter_key: str):
        del chapter_key
        if self._video_error:
            raise self._video_error
        return []

    def list_cached_course_videos(self, course_key: str):
        del course_key
        return []


class _MixedChapterClient:
    def __init__(self, unsupported_error=None) -> None:
        self._unsupported_error = unsupported_error or UnsupportedChapterError("当前章节没有可解析的视频任务点：电子教材（1.1）")

    def list_courses(self):
        return [_Course(course_key="course-1", title="线性代数")]

    def list_chapters(self, course_key: str):
        del course_key
        return [
            _Chapter(chapter_key="chapter-text", title="电子教材", order="1.1"),
            _Chapter(chapter_key="chapter-video", title="第一讲", order="1.2.1"),
        ]

    def list_videos(self, chapter_key: str):
        if chapter_key == "chapter-text":
            raise self._unsupported_error
        return [_Video(video_key="video-1", chapter_key=chapter_key, title="第一讲", duration=123)]

    def list_cached_course_videos(self, course_key: str):
        del course_key
        return []


class _CancelAfterFirstChapterClient:
    def __init__(self, *, tracker: InMemoryProgressTracker, task_id: str) -> None:
        self._tracker = tracker
        self._task_id = task_id
        self.video_calls: list[str] = []

    def list_courses(self):
        return [_Course(course_key="course-1", title="线性代数")]

    def list_chapters(self, course_key: str):
        del course_key
        return [
            _Chapter(chapter_key="chapter-1", title="第一章", order="1"),
            _Chapter(chapter_key="chapter-2", title="第二章", order="2"),
        ]

    def list_videos(self, chapter_key: str):
        self.video_calls.append(chapter_key)
        self._tracker.request_cancel(self._task_id)
        return [_Video(video_key="video-1", chapter_key=chapter_key, title="第一讲", duration=123)]

    def list_cached_course_videos(self, course_key: str):
        del course_key
        return []


class _CancelThenFailVideoClient:
    def __init__(self, *, tracker: InMemoryProgressTracker, task_id: str) -> None:
        self._tracker = tracker
        self._task_id = task_id

    def list_courses(self):
        return [_Course(course_key="course-1", title="线性代数")]

    def list_chapters(self, course_key: str):
        del course_key
        return [_Chapter(chapter_key="chapter-1", title="第一章", order="1")]

    def list_videos(self, chapter_key: str):
        del chapter_key
        self._tracker.request_cancel(self._task_id)
        raise RuntimeError("触发超星访问验证")

    def list_cached_course_videos(self, course_key: str):
        del course_key
        return []


class _BlockingImportClient:
    def __init__(self) -> None:
        self.import_entered = Event()
        self.release_import = Event()
        self.list_entered = Event()

    def list_courses(self):
        return [_Course(course_key="course-1", title="线性代数")]

    def list_chapters(self, course_key: str):
        del course_key
        self.import_entered.set()
        self.release_import.wait(timeout=1.0)
        return [_Chapter(chapter_key="chapter-1", title="第一章", order="1")]

    def list_videos(self, chapter_key: str):
        self.list_entered.set()
        return [_Video(video_key="video-1", chapter_key=chapter_key, title="第一讲", duration=123)]

    def list_cached_course_videos(self, course_key: str):
        del course_key
        return []


class UnsupportedChapterError(Exception):
    pass


class _UnusedDownloader:
    @classmethod
    def is_initialized(cls, *, state_dir: str, request_delay: float = 0.0) -> bool:
        del state_dir, request_delay
        return False


class _InitializedDownloader:
    @classmethod
    def is_initialized(cls, *, state_dir: str, request_delay: float = 0.0) -> bool:
        del state_dir, request_delay
        return True


class _RecordingInitDownloader:
    cancel_check = None
    request_delay = None
    course_delay = None

    @classmethod
    def init(
        cls,
        *,
        state_dir: str,
        timeout_seconds: int = 300,
        cancel_check=None,
        request_delay: float = 0.0,
        course_delay: float = 0.0,
    ):
        del state_dir, timeout_seconds
        cls.cancel_check = cancel_check
        cls.request_delay = request_delay
        cls.course_delay = course_delay
        return object()

    @classmethod
    def is_initialized(cls, *, state_dir: str, request_delay: float = 0.0) -> bool:
        del state_dir, request_delay
        return False


class _AntispiderDownloader:
    @classmethod
    def load(cls, *, state_dir: str, request_delay: float = 0.0):
        del state_dir, request_delay
        return cls()

    @classmethod
    def is_initialized(cls, *, state_dir: str, request_delay: float = 0.0) -> bool:
        del state_dir, request_delay
        return True

    def list_courses(self):
        raise _FakeHttpStatusError()

    def list_videos(self, chapter_key: str):
        del chapter_key
        raise _FakeHttpStatusError()


class _NetworkShouldNotBeCalledDownloader:
    @classmethod
    def load(cls, *, state_dir: str, request_delay: float = 0.0):
        del state_dir, request_delay
        raise AssertionError("list_courses should use cache before loading downloader")

    @classmethod
    def is_initialized(cls, *, state_dir: str, request_delay: float = 0.0) -> bool:
        del state_dir, request_delay
        return True


class _FakeResponse:
    url = "https://mooc1-1.chaoxing.com/antispiderShowVerify.ac"


class _FakeHttpStatusError(Exception):
    response = _FakeResponse()


class _RecordingDownloadClient:
    def __init__(self) -> None:
        self.calls = []

    def download_video(self, video_key, *, output_dir, filename, progress):
        self.calls.append(
            {
                "video_key": video_key,
                "output_dir": Path(output_dir),
                "filename": filename,
                "progress": progress,
            }
        )
        output = Path(output_dir) / filename
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")
        progress(1, 1)
        return output


class _CancellingDownloadClient:
    def __init__(self, tracker: InMemoryProgressTracker) -> None:
        self._tracker = tracker

    def download_video(self, video_key, *, output_dir, filename, progress):
        del video_key, output_dir, filename
        self._tracker.request_cancel("download/chaoxing-course-1/chaoxing-video-1")
        progress(0, 1)


if __name__ == "__main__":
    unittest.main()
