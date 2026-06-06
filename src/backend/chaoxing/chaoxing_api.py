from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable, Protocol

from backend.bilibili.ytdlp_bilibili import build_video_download_task_id
from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo


CHAOXING_PROVIDER = "chaoxing"
CHAOXING_CHROMIUM_REQUIRED_MESSAGE = "超星 Chromium 浏览器内核未下载，请先到下载管理下载。"
CHAOXING_INIT_CANCELLED_MESSAGE = "超星初始化已中断"
CHAOXING_ANTISPIDER_MESSAGE = "触发超星访问验证，请稍后重试，或重新 Init 超星后再导入。"
CHAOXING_REINIT_REQUIRED_MESSAGE = "超星登录态已失效，已清空本地 state，请重新 Init 后再导入。"
CHAOXING_ANTISPIDER_REINIT_THRESHOLD = 3


class ChaoxingDownloaderProtocol(Protocol):
    @classmethod
    def init(
        cls,
        *,
        state_dir: str,
        timeout_seconds: int = 300,
        cancel_check: Callable[[], bool] | None = None,
        request_delay: float = 0.0,
        course_delay: float = 0.0,
    ): ...

    @classmethod
    def load(cls, *, state_dir: str, request_delay: float = 0.0): ...

    @classmethod
    def is_initialized(cls, *, state_dir: str, request_delay: float = 0.0) -> bool: ...


class ProgressTracker(Protocol):
    def create_reporter(self, task_id: str) -> ProgressReporter: ...


class ChaoxingInitCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ChaoxingCourseRecord:
    course_key: str
    title: str
    teacher: str
    open_time: str


@dataclass(frozen=True)
class ChaoxingChapterRecord:
    chapter_key: str
    title: str
    order: str


@dataclass(frozen=True)
class ChaoxingVideoRecord:
    video_key: str
    chapter_key: str
    title: str
    duration: int
    filename: str


class ChaoxingDownloaderClient:
    def __init__(
        self,
        *,
        state_dir: Path,
        chromium_downloaded: Callable[[], bool],
        request_delay_seconds: float = 0.2,
        init_course_delay_seconds: float = 0.3,
        downloader_cls: ChaoxingDownloaderProtocol | None = None,
    ) -> None:
        self._state_dir = state_dir
        self._chromium_downloaded = chromium_downloaded
        self._request_delay_seconds = request_delay_seconds
        self._init_course_delay_seconds = init_course_delay_seconds
        self._downloader_cls = downloader_cls
        self._lock = Lock()
        self._init_cancel_event = Event()
        self._downloader = None
        self._antispider_counts: dict[str, int] = {}

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    def is_initialized(self) -> bool:
        return bool(
            self._require_downloader_cls().is_initialized(
                state_dir=str(self._state_dir),
                request_delay=self._request_delay_seconds,
            )
        )

    def init(self, *, timeout_seconds: int = 300):
        if not self._chromium_downloaded():
            raise RuntimeError(CHAOXING_CHROMIUM_REQUIRED_MESSAGE)
        with self._lock:
            self._init_cancel_event.clear()
            try:
                self._downloader = self._init_downloader(timeout_seconds=timeout_seconds)
            except ChaoxingInitCancelled:
                self._downloader = None
                raise
            return self._downloader

    def cancel_init(self) -> None:
        self._init_cancel_event.set()

    def load(self):
        with self._lock:
            if self._downloader is None:
                self._downloader = self._require_downloader_cls().load(
                    state_dir=str(self._state_dir),
                    request_delay=self._request_delay_seconds,
                )
            return self._downloader

    def list_courses(self):
        cached_courses = self._load_cached_courses()
        if cached_courses:
            return cached_courses
        return self._call_chaoxing_read("list_courses", lambda: self.load().list_courses())

    def list_chapters(self, course_key: str):
        cached_chapters = self._load_cached_chapters(course_key)
        if cached_chapters:
            return cached_chapters
        return self._call_chaoxing_read(f"list_chapters:{course_key}", lambda: self.load().list_chapters(course_key))

    def list_videos(self, chapter_key: str):
        cached_videos = self._load_cached_videos(chapter_key)
        if cached_videos:
            return cached_videos
        return self._call_chaoxing_read(f"list_videos:{chapter_key}", lambda: self.load().list_videos(chapter_key))

    def download_video(self, video_key: str, *, output_dir: Path, filename: str, progress):
        return _call_chaoxing(
            lambda: self.load().download_video(video_key, output_dir=output_dir, filename=filename, progress=progress)
        )

    def _init_downloader(self, *, timeout_seconds: int):
        downloader_cls = self._require_downloader_cls()
        try:
            return downloader_cls.init(
                state_dir=str(self._state_dir),
                timeout_seconds=timeout_seconds,
                cancel_check=self._init_cancel_event.is_set,
                request_delay=self._request_delay_seconds,
                course_delay=self._init_course_delay_seconds,
            )
        except Exception as error:
            if _is_chaoxing_init_cancelled(error) or _is_playwright_target_closed(error):
                raise ChaoxingInitCancelled(CHAOXING_INIT_CANCELLED_MESSAGE) from error
            raise

    def _require_downloader_cls(self):
        if self._downloader_cls is not None:
            return self._downloader_cls
        try:
            from chaoxing_downloader import ChaoxingDownloader
        except ModuleNotFoundError as error:
            if error.name != "chaoxing_downloader":
                raise
            raise RuntimeError("当前 Python 环境缺少 chaoxing-downloader 包，请先安装项目依赖。") from error

        return ChaoxingDownloader

    def _load_cached_courses(self) -> list[ChaoxingCourseRecord]:
        cache = self._load_cache()
        courses = cache.get("courses")
        if courses is None:
            return []
        if not isinstance(courses, list):
            raise RuntimeError(f"超星课程缓存格式错误：{self._cache_path()}")
        return [_course_record_from_cache(course, cache_path=self._cache_path()) for course in courses]

    def _load_cached_chapters(self, course_key: str) -> list[ChaoxingChapterRecord]:
        cache = self._load_cache()
        chapters = cache.get("chapters")
        if chapters is None:
            return []
        if not isinstance(chapters, list):
            raise RuntimeError(f"超星章节缓存格式错误：{self._cache_path()}")
        return [
            _chapter_record_from_cache(chapter, cache_path=self._cache_path())
            for chapter in chapters
            if isinstance(chapter, dict) and _text(chapter.get("course_key", "")) == course_key
        ]

    def _load_cached_videos(self, chapter_key: str) -> list[ChaoxingVideoRecord]:
        cache = self._load_cache()
        videos = cache.get("videos")
        if videos is None:
            return []
        if not isinstance(videos, list):
            raise RuntimeError(f"超星视频缓存格式错误：{self._cache_path()}")
        return [
            _video_record_from_cache(video, cache_path=self._cache_path())
            for video in videos
            if isinstance(video, dict) and _text(video.get("chapter_key", "")) == chapter_key
        ]

    def _load_cache(self) -> dict:
        cache_path = self._cache_path()
        if not cache_path.exists():
            return {}
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            raise RuntimeError(f"超星缓存格式错误：{cache_path}")
        return cache

    def _cache_path(self) -> Path:
        cache_path = self._state_dir / "cache.json"
        return cache_path

    def _call_chaoxing_read(self, target_key: str, call):
        try:
            result = _call_chaoxing(call)
            self._antispider_counts.pop(target_key, None)
            return result
        except RuntimeError as error:
            if CHAOXING_ANTISPIDER_MESSAGE not in str(error):
                raise
            count = self._antispider_counts.get(target_key, 0) + 1
            self._antispider_counts[target_key] = count
            if count >= CHAOXING_ANTISPIDER_REINIT_THRESHOLD:
                self._clear_state_after_antispider()
                raise RuntimeError(CHAOXING_REINIT_REQUIRED_MESSAGE) from error
            raise

    def _clear_state_after_antispider(self) -> None:
        with self._lock:
            self._downloader = None
            self._antispider_counts.clear()
            if self._state_dir.exists():
                shutil.rmtree(self._state_dir)


class ChaoxingCourseImporter:
    def __init__(self, *, client: ChaoxingDownloaderClient) -> None:
        self._client = client

    def is_initialized(self) -> bool:
        return self._client.is_initialized()

    def init(self):
        return self._client.init()

    def cancel_init(self) -> None:
        self._client.cancel_init()

    def list_courses(self) -> list[ChaoxingCourseRecord]:
        return [_to_course_record(course) for course in self._client.list_courses()]

    def list_chapters(self, course_key: str) -> list[ChaoxingChapterRecord]:
        return [_to_chapter_record(chapter) for chapter in self._client.list_chapters(course_key)]

    def list_videos(self, chapter_key: str) -> list[ChaoxingVideoRecord]:
        return [_to_video_record(video) for video in self._client.list_videos(chapter_key)]

    def import_course(self, course_key: str, *, progress: ProgressReporter | None = None) -> LinkedSeries:
        courses = list(self._client.list_courses())
        course = next((item for item in courses if _text(getattr(item, "course_key", "")) == course_key), None)
        if course is None:
            raise LookupError(f"chaoxing course not found: {course_key}")
        course_title = _text(getattr(course, "title", "")) or course_key

        videos: list[LinkedVideo] = []
        try:
            chapters = self._client.list_chapters(course_key)
        except RuntimeError as error:
            raise RuntimeError(f"读取超星课程章节失败：{course_title}；{error}") from error

        total_chapters = len(chapters)
        skipped_chapters = 0
        for chapter_index, chapter in enumerate(chapters, start=1):
            chapter_title = _text(getattr(chapter, "title", ""))
            chapter_key = _text(getattr(chapter, "chapter_key", ""))
            if progress is not None:
                progress.update(
                    "import",
                    _import_progress(chapter_index - 1, total_chapters),
                    f"正在解析视频章节 {chapter_index}/{total_chapters}：{chapter_title or chapter_key}",
                )
            try:
                chapter_videos = self._client.list_videos(chapter_key)
            except Exception as error:
                if _is_unsupported_chapter(error):
                    skipped_chapters += 1
                    if progress is not None:
                        progress.update(
                            "import",
                            _import_progress(chapter_index, total_chapters),
                            f"跳过非视频章节 {chapter_index}/{total_chapters}：{chapter_title or chapter_key}",
                        )
                    continue
                if not isinstance(error, RuntimeError):
                    raise
                raise RuntimeError(f"读取超星章节视频失败：{chapter_title or chapter_key}；{error}") from error
            for video in chapter_videos:
                video_key = _text(getattr(video, "video_key", ""))
                if not video_key:
                    raise RuntimeError("chaoxing video missing video_key")
                title = _text(getattr(video, "title", "")) or _text(getattr(video, "filename", "")) or video_key
                videos.append(
                    LinkedVideo(
                        bvid=f"chaoxing-{_safe_key(video_key)}",
                        page=1,
                        title=f"{chapter_title} - {title}" if chapter_title and chapter_title not in title else title,
                        cover_url="",
                        duration_seconds=_positive_int(getattr(video, "duration", 0)),
                        source_url=f"chaoxing://video/{video_key}",
                        provider=CHAOXING_PROVIDER,
                        download_key=video_key,
                    )
                )
            if progress is not None:
                progress.update(
                    "import",
                    _import_progress(chapter_index, total_chapters),
                    f"正在解析视频章节 {chapter_index}/{total_chapters}，已发现 {len(videos)} 个视频，已跳过 {skipped_chapters} 个非视频章节",
                )

        if not videos:
            raise RuntimeError(f"超星课程没有可导入视频：{course_title}")

        return LinkedSeries(
            series_id=f"chaoxing-{_safe_key(course_key)}",
            title=course_title,
            cover_url="",
            source_url=f"chaoxing://course/{course_key}",
            videos=videos,
        )


class ChaoxingLinkedVideoDownloadStarter:
    def __init__(
        self,
        *,
        root_dir: Path,
        client: ChaoxingDownloaderClient,
        progress_tracker: ProgressTracker,
        run_in_background: bool = True,
    ) -> None:
        self._root_dir = root_dir
        self._client = client
        self._progress_tracker = progress_tracker
        self._run_in_background = run_in_background

    def start(self, *, series_id: str, video: LinkedVideo) -> str:
        if video.provider != CHAOXING_PROVIDER:
            raise RuntimeError(f"unsupported linked video provider '{video.provider}'")
        if not video.download_key:
            raise RuntimeError(f"chaoxing linked video missing download_key: {video.video_id}")
        task_id = build_video_download_task_id(series_id, video.video_id)
        reporter = self._progress_tracker.create_reporter(task_id)
        dest_dir = self._root_dir / "videos" / series_id

        def _run() -> None:
            try:
                reporter.update("download", 0.0, "开始下载超星视频")
                self._client.download_video(
                    video.download_key,
                    output_dir=dest_dir,
                    filename=f"{video.video_id}.mp4",
                    progress=lambda downloaded, total: _report_download_progress(reporter, downloaded, total),
                )
                reporter.completed(f"下载完成：{video.video_id}.mp4")
            except Exception as error:
                reporter.failed(str(error))

        if self._run_in_background:
            Thread(target=_run, daemon=True).start()
        else:
            _run()
        return task_id


def run_blocking(call):
    return asyncio.to_thread(call)


def _report_download_progress(reporter: ProgressReporter, downloaded: int, total: int | None) -> None:
    if total and total > 0:
        progress = max(0.0, min(100.0, downloaded / total * 100.0))
        reporter.update("download", progress, f"下载中 {progress:.1f}%")
        return
    reporter.update("download", None, f"已下载 {downloaded} bytes")


def _import_progress(completed: int, total: int) -> float | None:
    if total <= 0:
        return None
    return max(0.0, min(100.0, completed / total * 100.0))


def _to_course_record(course) -> ChaoxingCourseRecord:
    return ChaoxingCourseRecord(
        course_key=_text(getattr(course, "course_key", "")),
        title=_text(getattr(course, "title", "")),
        teacher=_text(getattr(course, "teacher", "")),
        open_time=_text(getattr(course, "open_time", "")),
    )


def _course_record_from_cache(course: object, *, cache_path: Path) -> ChaoxingCourseRecord:
    if not isinstance(course, dict):
        raise RuntimeError(f"超星课程缓存格式错误：{cache_path}")
    return ChaoxingCourseRecord(
        course_key=_text(course.get("course_key", "")),
        title=_text(course.get("title", "")),
        teacher=_text(course.get("teacher", "")),
        open_time=_text(course.get("open_time", "")),
    )


def _chapter_record_from_cache(chapter: object, *, cache_path: Path) -> ChaoxingChapterRecord:
    if not isinstance(chapter, dict):
        raise RuntimeError(f"超星章节缓存格式错误：{cache_path}")
    return ChaoxingChapterRecord(
        chapter_key=_text(chapter.get("chapter_key", "")),
        title=_text(chapter.get("title", "")),
        order=_text(chapter.get("order", "")),
    )


def _video_record_from_cache(video: object, *, cache_path: Path) -> ChaoxingVideoRecord:
    if not isinstance(video, dict):
        raise RuntimeError(f"超星视频缓存格式错误：{cache_path}")
    return ChaoxingVideoRecord(
        video_key=_text(video.get("video_key", "")),
        chapter_key=_text(video.get("chapter_key", "")),
        title=_text(video.get("title", "")),
        duration=_positive_int(video.get("duration", 0)),
        filename=_text(video.get("filename", "")),
    )


def _to_chapter_record(chapter) -> ChaoxingChapterRecord:
    return ChaoxingChapterRecord(
        chapter_key=_text(getattr(chapter, "chapter_key", "")),
        title=_text(getattr(chapter, "title", "")),
        order=_text(getattr(chapter, "order", "")),
    )


def _to_video_record(video) -> ChaoxingVideoRecord:
    return ChaoxingVideoRecord(
        video_key=_text(getattr(video, "video_key", "")),
        chapter_key=_text(getattr(video, "chapter_key", "")),
        title=_text(getattr(video, "title", "")),
        duration=_positive_int(getattr(video, "duration", 0)),
        filename=_text(getattr(video, "filename", "")),
    )


def _safe_key(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return normalized or "item"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else str(value or "").strip()


def _positive_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return 0


def _is_playwright_target_closed(error: BaseException) -> bool:
    return error.__class__.__name__ == "TargetClosedError"


def _is_chaoxing_init_cancelled(error: BaseException) -> bool:
    return error.__class__.__name__ == "InitCancelled"


def _is_unsupported_chapter(error: BaseException) -> bool:
    return error.__class__.__name__ == "UnsupportedChapterError" or "未解析到课程章节" in str(error)


def _call_chaoxing(call):
    try:
        return call()
    except Exception as error:
        antispider_url = _chaoxing_antispider_url(error)
        if antispider_url:
            raise RuntimeError(
                f"{CHAOXING_ANTISPIDER_MESSAGE} 命中地址：{antispider_url}；底层异常：{error.__class__.__name__}"
            ) from error
        raise


def _is_chaoxing_antispider(error: BaseException) -> bool:
    return bool(_chaoxing_antispider_url(error))


def _chaoxing_antispider_url(error: BaseException) -> str:
    response = getattr(error, "response", None)
    url = str(getattr(response, "url", ""))
    return url if "antispiderShowVerify.ac" in url else ""
