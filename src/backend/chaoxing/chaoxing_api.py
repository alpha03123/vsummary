"""超星（Chaoxing）课程导入适配器。

封装 ``chaoxing-downloader`` 第三方库的初始化、登录、课程列表查询、
视频列表查询与下载功能，把超星课程/章节/视频结构映射为 vsummary 库内可
处理的 ``LinkedSeries`` / ``LinkedVideo`` 模型。

导入流程：
1. 用户通过前端触发 ``init`` → 启动浏览器完成登录；
2. 登录后 ``list_courses`` / ``list_chapters`` / ``list_videos`` 查询课程结构；
3. ``import_course`` 把选中的课程转为 ``LinkedSeries``；
4. 后台下载器按需拉取视频文件。
"""

from __future__ import annotations

import asyncio
import inspect
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
CHAOXING_INIT_CANCELLED_MESSAGE = "超星初始化已中断"
CHAOXING_ANTISPIDER_MESSAGE = "触发超星访问验证，请稍后重试，或重新 Init 超星后再导入。"
CHAOXING_REINIT_REQUIRED_MESSAGE = "超星登录态已失效，已清空本地 state，请重新 Init 后再导入。"
CHAOXING_ANTISPIDER_REINIT_THRESHOLD = 1


class ChaoxingDownloaderProtocol(Protocol):
    """chaoxing-downloader 库的 Protocol 定义。

    声明 ``init``/``load``/``is_initialized`` 三个类方法签名，
    方便在容器注入时替换为 mock 实现。
    """

    @classmethod
    def init(
        cls,
        *,
        state_dir: str,
        timeout_seconds: int = 300,
        login_url: str | None = None,
        browser_port: int | None = None,
        collect_impl: object,
        cancel_check: Callable[[], bool] | None = None,
        request_delay: float = 0.0,
        course_delay: float = 0.0,
    ): ...

    @classmethod
    def load(cls, *, state_dir: str, request_delay: float = 0.0): ...

    @classmethod
    def is_initialized(cls, *, state_dir: str, request_delay: float = 0.0) -> bool: ...


class ProgressTracker(Protocol):
    """进度报告器的工厂端口（Protocol）。

    每次下载/导入对应一个独立的 ``task_id``，创建对应的 ``ProgressReporter``。
    """

    def create_reporter(self, task_id: str) -> ProgressReporter: ...


class ChaoxingInitCancelled(RuntimeError):
    """超星初始化（登录）被用户取消时抛出的异常。"""


class ChaoxingDownloadCancelled(RuntimeError):
    """超星视频下载被用户取消时抛出的异常。"""


class ChaoxingImportCancelled(RuntimeError):
    """超星课程导入被用户取消时抛出的异常。"""


@dataclass(frozen=True)
class ChaoxingCourseRecord:
    """超星课程记录（不可变 DTO）。"""
    course_key: str
    title: str
    teacher: str
    open_time: str


@dataclass(frozen=True)
class ChaoxingChapterRecord:
    """超星课程章节记录（不可变 DTO）。"""

    chapter_key: str
    title: str
    order: str


@dataclass(frozen=True)
class ChaoxingVideoRecord:
    """超星章节视频记录（不可变 DTO）。"""
    video_key: str
    chapter_key: str
    title: str
    duration: int
    filename: str


class ChaoxingDownloaderClient:
    """超星下载器客户端——封装 chaoxing-downloader 库的生命周期管理。

    负责初始化的启停控制、请求延迟配置、反爬计数与本地 state 缓存处理；
    对上层（``ChaoxingCourseImporter``）提供课程/章节/视频的查询与下载接口。

    关键不变量：所有对下载器状态的修改均在 ``self._lock`` 保护下进行；
    反爬触发超过阈值时自动清空本地 state 并要求重新登录。
    """

    def __init__(
        self,
        *,
        state_dir: Path,
        request_delay_seconds: float = 0.2,
        init_course_delay_seconds: float = 0.3,
        downloader_cls: ChaoxingDownloaderProtocol | None = None,
    ) -> None:
        self._state_dir = state_dir
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
        """检查 chaoxing-downloader 是否已完成初始化（登录态有效）。

        Returns:
            已初始化则返回 ``True``。
        """
        return bool(
            self._require_downloader_cls().is_initialized(
                state_dir=str(self._state_dir),
                request_delay=self._request_delay_seconds,
            )
        )

    def init(self, *, timeout_seconds: int = 300):
        """启动超星浏览器登录流程。

        在锁保护下调用 ``ChaoxingDownloader.init``，阻塞直到登录成功
        或超时/取消；登录态的 state 文件保存在 ``self._state_dir``。

        Args:
            timeout_seconds: 登录等待超时秒数，默认 300。

        Returns:
            初始化完成的 ``ChaoxingDownloader`` 实例。

        Raises:
            ChaoxingInitCancelled: 用户在浏览器登录过程中取消。
        """
        with self._lock:
            self._init_cancel_event.clear()
            try:
                self._downloader = self._init_downloader(timeout_seconds=timeout_seconds)
            except ChaoxingInitCancelled:
                self._downloader = None
                raise
            return self._downloader

    def cancel_init(self) -> None:
        """设置取消信号，中断正在进行的浏览器登录流程。"""
        self._init_cancel_event.set()

    def configure_delays(self, *, request_delay_seconds: float, init_course_delay_seconds: float) -> None:
        """更新请求延迟参数并清除现有下载器实例。

        延迟参数变更后需要重新 ``load`` 才能生效。

        Args:
            request_delay_seconds: 每次 API 请求间的延迟秒数。
            init_course_delay_seconds: 课程初始化阶段的延迟秒数。
        """
        with self._lock:
            self._request_delay_seconds = request_delay_seconds
            self._init_course_delay_seconds = init_course_delay_seconds
            self._downloader = None

    def load(self):
        """加载（或重新加载）chaoxing-downloader 实例。

        若实例为 ``None`` 则调用 ``ChaoxingDownloader.load`` 从本地 state
        文件恢复登录态；否则直接返回已有实例。

        Returns:
            ``ChaoxingDownloader`` 实例。
        """
        with self._lock:
            if self._downloader is None:
                self._downloader = self._require_downloader_cls().load(
                    state_dir=str(self._state_dir),
                    request_delay=self._request_delay_seconds,
                )
            return self._downloader

    def list_courses(self):
        """列出登录用户的所有超星课程（优先从本地缓存读取）。

        Returns:
            ``ChaoxingCourseRecord`` 列表（chaoxing-downloader 原生对象）。
        """
        cached_courses = self._load_cached_courses()
        if cached_courses:
            return cached_courses
        return self._call_chaoxing_read("list_courses", lambda: self.load().list_courses())

    def list_chapters(self, course_key: str):
        """列出指定课程的章节列表（优先从本地缓存读取）。

        Args:
            course_key: 课程唯一键。

        Returns:
            ``ChaoxingChapterRecord`` 列表。
        """
        cached_chapters = self._load_cached_chapters(course_key)
        if cached_chapters:
            return cached_chapters
        return self._call_chaoxing_read(f"list_chapters:{course_key}", lambda: self.load().list_chapters(course_key))

    def list_videos(self, chapter_key: str):
        """列出指定章节下的视频列表（优先从本地缓存读取）。

        Args:
            chapter_key: 章节唯一键。

        Returns:
            ``ChaoxingVideoRecord`` 列表。
        """
        cached_videos = self._load_cached_videos(chapter_key)
        if cached_videos:
            return cached_videos
        return self._call_chaoxing_read(f"list_videos:{chapter_key}", lambda: self.load().list_videos(chapter_key))

    def list_cached_course_videos(self, course_key: str) -> list[ChaoxingVideoRecord]:
        """仅从本地缓存中读取课程的所有视频（不发网络请求）。

        Args:
            course_key: 课程唯一键。

        Returns:
            ``ChaoxingVideoRecord`` 列表。
        """
        return self._load_cached_course_videos(course_key)

    def download_video(self, video_key: str, *, output_dir: Path, filename: str, progress):
        """下载超星视频文件到本地。

        通过 ``_call_chaoxing`` 包装反爬检测；下载进度通过 ``progress``
        回调上报。

        Args:
            video_key: 超星视频的唯一键。
            output_dir: 下载目标目录。
            filename: 输出文件名（如 ``"video_01.mp4"``）。
            progress: ``(downloaded_bytes, total_bytes)`` 回调。
        """
        return _call_chaoxing(
            lambda: self.load().download_video(video_key, output_dir=output_dir, filename=filename, progress=progress)
        )

    def _init_downloader(self, *, timeout_seconds: int):
        """调用 chaoxing-downloader 的 ``init`` 方法并处理取消/异常。

        Args:
            timeout_seconds: 登录超时秒数。

        Returns:
            初始化完成的 ``ChaoxingDownloader`` 实例。

        Raises:
            ChaoxingInitCancelled: 用户在登录过程中取消。
        """
        downloader_cls = self._require_downloader_cls()
        _validate_downloader_init_signature(downloader_cls)
        try:
            return downloader_cls.init(
                state_dir=str(self._state_dir),
                timeout_seconds=timeout_seconds,
                cancel_check=self._init_cancel_event.is_set,
                request_delay=self._request_delay_seconds,
                course_delay=self._init_course_delay_seconds,
            )
        except Exception as error:
            if _is_chaoxing_init_cancelled(error):
                raise ChaoxingInitCancelled(CHAOXING_INIT_CANCELLED_MESSAGE) from error
            raise

    def _require_downloader_cls(self):
        """获取 chaoxing-downloader 类引用（优先使用注入的 mock）。

        Returns:
            ``ChaoxingDownloader`` 类引用。

        Raises:
            RuntimeError: chaoxing-downloader 包未安装。
        """
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
        """从本地缓存文件加载课程列表。

        Returns:
            ``ChaoxingCourseRecord`` 列表；无缓存返回空列表。
        """
        cache = self._load_cache()
        courses = cache.get("courses")
        if courses is None:
            return []
        if not isinstance(courses, list):
            raise RuntimeError(f"超星课程缓存格式错误：{self._cache_path()}")
        return [_course_record_from_cache(course, cache_path=self._cache_path()) for course in courses]

    def _load_cached_chapters(self, course_key: str) -> list[ChaoxingChapterRecord]:
        """从本地缓存加载指定课程的章节列表。

        Args:
            course_key: 课程唯一键。

        Returns:
            ``ChaoxingChapterRecord`` 列表。
        """
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
        """从本地缓存加载指定章节的视频列表。

        Args:
            chapter_key: 章节唯一键。

        Returns:
            ``ChaoxingVideoRecord`` 列表。
        """
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

    def _load_cached_course_videos(self, course_key: str) -> list[ChaoxingVideoRecord]:
        """从本地缓存加载指定课程下所有视频（跨章节聚合）。

        Args:
            course_key: 课程唯一键。

        Returns:
            ``ChaoxingVideoRecord`` 列表。
        """
        cache = self._load_cache()
        videos = cache.get("videos")
        if videos is None:
            return []
        if not isinstance(videos, list):
            raise RuntimeError(f"超星视频缓存格式错误：{self._cache_path()}")
        return [
            _video_record_from_cache(video, cache_path=self._cache_path())
            for video in videos
            if isinstance(video, dict) and _text(video.get("course_key", "")) == course_key
        ]

    def _load_cache(self) -> dict:
        """加载超星本地 state 缓存（``cache.json``）。

        Returns:
            缓存字典；文件不存在时返回空字典。
        """
        cache_path = self._cache_path()
        if not cache_path.exists():
            return {}
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            raise RuntimeError(f"超星缓存格式错误：{cache_path}")
        return cache

    def _cache_path(self) -> Path:
        """返回超星本地缓存文件路径（``state_dir/cache.json``）。

        Returns:
            缓存文件的 ``Path``。
        """
        cache_path = self._state_dir / "cache.json"
        return cache_path

    def _call_chaoxing_read(self, target_key: str, call):
        """包装 chaoxing-downloader 的只读调用并处理反爬逻辑。

        反爬计数按 ``target_key`` 分桶；命中超星访问验证时递增计数，
        达到 ``CHAOXING_ANTISPIDER_REINIT_THRESHOLD`` 时清空本地 state
        并要求重新登录。

        Args:
            target_key: 反爬计数的桶键。
            call: 实际调用 lambda。
        """
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
        """清空超星本地 state：清除下载器实例、反爬计数并删除 state 目录。"""
        with self._lock:
            self._downloader = None
            self._antispider_counts.clear()
            if self._state_dir.exists():
                shutil.rmtree(self._state_dir)


class ChaoxingCourseImporter:
    """超星课程导入器——把超星课程结构映射为库内 ``LinkedSeries``。

    课程 → 系列，章节 → 分组，视频 → ``LinkedVideo``；
    导入在 ``_import_lock`` 保护下串行执行，避免并发冲突。

    导入流程：
    1. 查询课程下的全部章节（支持从本地缓存读取）；
    2. 若已缓存视频列表则直接映射，否则逐章节查询视频；
    3. 跳过非视频章节（如纯文本/测验章节）；
    4. 最终组装为 ``LinkedSeries`` 返回。
    """

    def __init__(self, *, client: ChaoxingDownloaderClient) -> None:
        self._client = client
        self._import_lock = Lock()

    def is_initialized(self) -> bool:
        """检查超星登录态是否有效。

        Returns:
            已初始化则返回 ``True``。
        """
        return self._client.is_initialized()

    def init(self):
        """启动超星浏览器登录流程（委托给 ``ChaoxingDownloaderClient.init``）。"""
        return self._client.init()

    def cancel_init(self) -> None:
        """取消正在进行的浏览器登录流程。"""
        self._client.cancel_init()

    def configure_delays(self, *, request_delay_seconds: float, init_course_delay_seconds: float) -> None:
        """配置请求延迟参数（导入锁保护）。

        Args:
            request_delay_seconds: API 请求间隔（秒）。
            init_course_delay_seconds: 课程初始化延迟（秒）。
        """
        with self._import_lock:
            self._client.configure_delays(
                request_delay_seconds=request_delay_seconds,
                init_course_delay_seconds=init_course_delay_seconds,
            )

    def list_courses(self) -> list[ChaoxingCourseRecord]:
        """列出登录用户的所有超星课程（转为 DTO）。

        Returns:
            ``ChaoxingCourseRecord`` DTO 列表。
        """
        with self._import_lock:
            return [_to_course_record(course) for course in self._client.list_courses()]

    def list_chapters(self, course_key: str) -> list[ChaoxingChapterRecord]:
        """列出指定课程的章节（转为 DTO）。

        Args:
            course_key: 课程唯一键。

        Returns:
            ``ChaoxingChapterRecord`` DTO 列表。
        """
        with self._import_lock:
            return [_to_chapter_record(chapter) for chapter in self._client.list_chapters(course_key)]

    def list_videos(self, chapter_key: str) -> list[ChaoxingVideoRecord]:
        """列出指定章节的视频（转为 DTO）。

        Args:
            chapter_key: 章节唯一键。

        Returns:
            ``ChaoxingVideoRecord`` DTO 列表。
        """
        with self._import_lock:
            return [_to_video_record(video) for video in self._client.list_videos(chapter_key)]

    def import_course(self, course_key: str, *, progress: ProgressReporter | None = None) -> LinkedSeries:
        """将超星课程导入为 ``LinkedSeries``。

        在 ``_import_lock`` 保护下串行执行，导入期间轮询取消信号；
        支持从本地缓存直接读取视频列表以加速重复导入。

        Args:
            course_key: 课程唯一键。
            progress: 可选的进度报告器（导入期间滚动更新章节进度）。

        Returns:
            包含视频列表与系列元信息的 ``LinkedSeries``。

        Raises:
            LookupError: 课程未找到。
            ChaoxingImportCancelled: 用户取消导入。
            RuntimeError: 章节读取失败或课程无视频。
        """
        while not self._import_lock.acquire(timeout=0.1):
            _raise_if_import_cancelled(progress)
        try:
            return self._import_course_unlocked(course_key, progress=progress)
        finally:
            self._import_lock.release()

    def _import_course_unlocked(self, course_key: str, *, progress: ProgressReporter | None = None) -> LinkedSeries:
        """实际的导入逻辑（调用方已持有 ``_import_lock``）。

        优先从本地缓存读取视频列表；否则逐章节查询并跳过非视频章节。

        Args:
            course_key: 课程唯一键。
            progress: 可选的进度报告器。

        Returns:
            ``LinkedSeries`` 对象。
        """
        _raise_if_import_cancelled(progress)
        courses = list(self._client.list_courses())
        course = next((item for item in courses if _text(getattr(item, "course_key", "")) == course_key), None)
        if course is None:
            raise LookupError(f"chaoxing course not found: {course_key}")
        course_title = _text(getattr(course, "title", "")) or course_key

        videos: list[LinkedVideo] = []
        try:
            _raise_if_import_cancelled(progress)
            chapters = self._client.list_chapters(course_key)
        except RuntimeError as error:
            _raise_if_import_cancelled(progress)
            raise RuntimeError(f"读取超星课程章节失败：{course_title}；{error}") from error

        total_chapters = len(chapters)
        cached_course_videos = self._client.list_cached_course_videos(course_key)
        if cached_course_videos:
            chapter_titles = {
                _text(getattr(chapter, "chapter_key", "")): _text(getattr(chapter, "title", ""))
                for chapter in chapters
            }
            for video in cached_course_videos:
                videos.append(_to_linked_video(video, chapter_title=chapter_titles.get(video.chapter_key, "")))
            if progress is not None:
                progress.update(
                    "import",
                    _import_progress(total_chapters, total_chapters),
                    f"已从超星课程缓存读取 {len(videos)} 个视频",
                )
            return _to_linked_series(course_key=course_key, course_title=course_title, videos=videos)

        skipped_chapters = 0
        for chapter_index, chapter in enumerate(chapters, start=1):
            _raise_if_import_cancelled(progress)
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
                _raise_if_import_cancelled(progress)
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
            _raise_if_import_cancelled(progress)
            for video in chapter_videos:
                videos.append(_to_linked_video(video, chapter_title=chapter_title))
            if progress is not None:
                progress.update(
                    "import",
                    _import_progress(chapter_index, total_chapters),
                    f"正在解析视频章节 {chapter_index}/{total_chapters}，已发现 {len(videos)} 个视频，已跳过 {skipped_chapters} 个非视频章节",
                )

        _raise_if_import_cancelled(progress)
        if not videos:
            raise RuntimeError(f"超星课程没有可导入视频：{course_title}")

        return _to_linked_series(course_key=course_key, course_title=course_title, videos=videos)


class ChaoxingLinkedVideoDownloadStarter:
    """超星视频后台下载启动器。

    校验 ``video.provider == "chaoxing"`` 后启动下载线程；
    支持前台阻塞与后台 daemon 两种模式，通过 ``run_in_background`` 控制。
    """

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
        """启动超星视频下载并返回任务 ID。

        根据 ``run_in_background`` 配置决定在后台线程或当前线程执行。

        Args:
            series_id: 系列 ID。
            video: 含 ``download_key`` 和 ``provider`` 的 ``LinkedVideo``。

        Returns:
            可被前端订阅的下载任务 ID。

        Raises:
            RuntimeError: provider 不是 ``"chaoxing"`` 或缺少 ``download_key``。
        """
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
                    progress=lambda downloaded, total: _report_download_progress_or_cancel(reporter, downloaded, total),
                )
                reporter.completed(f"下载完成：{video.video_id}.mp4")
            except ChaoxingDownloadCancelled as error:
                reporter.cancelled(str(error))
            except Exception as error:
                reporter.failed(str(error))

        if self._run_in_background:
            Thread(target=_run, daemon=True).start()
        else:
            _run()
        return task_id


def run_blocking(call):
    """将同步调用提交到线程池，返回可 await 的协程（等同于 ``asyncio.to_thread``）。

    Args:
        call: 同步调用 lambda。

    Returns:
        可 await 的协程对象。
    """
    return asyncio.to_thread(call)


def _report_download_progress(reporter: ProgressReporter, downloaded: int, total: int | None) -> None:
    """计算并上报下载进度百分比。

    Args:
        reporter: 进度报告器。
        downloaded: 已下载字节数。
        total: 总字节数；若为 ``None`` 则仅上报已下载字节数。
    """
    if total and total > 0:
        progress = max(0.0, min(100.0, downloaded / total * 100.0))
        reporter.update("download", progress, f"下载中 {progress:.1f}%")
        return
    reporter.update("download", None, f"已下载 {downloaded} bytes")


def _report_download_progress_or_cancel(reporter: ProgressReporter, downloaded: int, total: int | None) -> None:
    """先检查取消信号再上报下载进度；取消时抛出 ``ChaoxingDownloadCancelled``。

    Args:
        reporter: 进度报告器。
        downloaded: 已下载字节数。
        total: 总字节数。

    Raises:
        ChaoxingDownloadCancelled: 用户取消下载。
    """
    try:
        reporter.raise_if_cancelled()
    except RuntimeError as error:
        raise ChaoxingDownloadCancelled("下载已取消") from error
    _report_download_progress(reporter, downloaded, total)


def _import_progress(completed: int, total: int) -> float | None:
    """计算导入进度百分比（用于进度报告器）。

    Args:
        completed: 已完成数。
        total: 总数。

    Returns:
        百分比浮点数（0~100）；total <= 0 时返回 ``None``。
    """
    if total <= 0:
        return None
    return max(0.0, min(100.0, completed / total * 100.0))


def _to_course_record(course) -> ChaoxingCourseRecord:
    """将 chaoxing-downloader 原生 course 对象转为 DTO。

    Args:
        course: chaoxing-downloader 的课程对象。

    Returns:
        ``ChaoxingCourseRecord`` DTO。
    """
    return ChaoxingCourseRecord(
        course_key=_text(getattr(course, "course_key", "")),
        title=_text(getattr(course, "title", "")),
        teacher=_text(getattr(course, "teacher", "")),
        open_time=_text(getattr(course, "open_time", "")),
    )


def _course_record_from_cache(course: object, *, cache_path: Path) -> ChaoxingCourseRecord:
    """从缓存字典构建课程 DTO（含格式校验）。

    Args:
        course: 课程缓存 dict。
        cache_path: 用于错误信息的缓存文件路径。

    Returns:
        ``ChaoxingCourseRecord`` DTO。

    Raises:
        RuntimeError: 缓存格式不是 dict。
    """
    if not isinstance(course, dict):
        raise RuntimeError(f"超星课程缓存格式错误：{cache_path}")
    return ChaoxingCourseRecord(
        course_key=_text(course.get("course_key", "")),
        title=_text(course.get("title", "")),
        teacher=_text(course.get("teacher", "")),
        open_time=_text(course.get("open_time", "")),
    )


def _chapter_record_from_cache(chapter: object, *, cache_path: Path) -> ChaoxingChapterRecord:
    """从缓存字典构建章节 DTO（含格式校验）。

    Args:
        chapter: 章节缓存 dict。
        cache_path: 用于错误信息的缓存文件路径。

    Returns:
        ``ChaoxingChapterRecord`` DTO。
    """
    if not isinstance(chapter, dict):
        raise RuntimeError(f"超星章节缓存格式错误：{cache_path}")
    return ChaoxingChapterRecord(
        chapter_key=_text(chapter.get("chapter_key", "")),
        title=_text(chapter.get("title", "")),
        order=_text(chapter.get("order", "")),
    )


def _video_record_from_cache(video: object, *, cache_path: Path) -> ChaoxingVideoRecord:
    """从缓存字典构建视频 DTO（含格式校验）。

    Args:
        video: 视频缓存 dict。
        cache_path: 用于错误信息的缓存文件路径。

    Returns:
        ``ChaoxingVideoRecord`` DTO。
    """
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
    """将 chaoxing-downloader 原生 chapter 对象转为 DTO。

    Args:
        chapter: chaoxing-downloader 的章节对象。

    Returns:
        ``ChaoxingChapterRecord`` DTO。
    """
    return ChaoxingChapterRecord(
        chapter_key=_text(getattr(chapter, "chapter_key", "")),
        title=_text(getattr(chapter, "title", "")),
        order=_text(getattr(chapter, "order", "")),
    )


def _to_video_record(video) -> ChaoxingVideoRecord:
    """将 chaoxing-downloader 原生 video 对象转为 DTO。

    Args:
        video: chaoxing-downloader 的视频对象。

    Returns:
        ``ChaoxingVideoRecord`` DTO。
    """
    return ChaoxingVideoRecord(
        video_key=_text(getattr(video, "video_key", "")),
        chapter_key=_text(getattr(video, "chapter_key", "")),
        title=_text(getattr(video, "title", "")),
        duration=_positive_int(getattr(video, "duration", 0)),
        filename=_text(getattr(video, "filename", "")),
    )


def _to_linked_video(video, *, chapter_title: str) -> LinkedVideo:
    """将超星视频转为库内通用的 ``LinkedVideo`` 模型。

    Args:
        video: 超星视频记录（含 ``video_key``、``title``、``duration``、``filename``）。
        chapter_title: 所属章节标题（会拼接到视频标题前）。

    Returns:
        用于 vsummary 库内存储的 ``LinkedVideo``。
    """
    video_key = _text(getattr(video, "video_key", ""))
    if not video_key:
        raise RuntimeError("chaoxing video missing video_key")
    title = _text(getattr(video, "title", "")) or _text(getattr(video, "filename", "")) or video_key
    return LinkedVideo(
        bvid=f"chaoxing-{_safe_key(video_key)}",
        page=1,
        title=f"{chapter_title} - {title}" if chapter_title and chapter_title not in title else title,
        cover_url="",
        duration_seconds=_positive_int(getattr(video, "duration", 0)),
        source_url=f"chaoxing://video/{video_key}",
        provider=CHAOXING_PROVIDER,
        download_key=video_key,
    )


def _to_linked_series(*, course_key: str, course_title: str, videos: list[LinkedVideo]) -> LinkedSeries:
    """将超星课程信息组装为库内的 ``LinkedSeries``。

    Args:
        course_key: 课程唯一键。
        course_title: 课程标题。
        videos: 已转换的 ``LinkedVideo`` 列表。

    Returns:
        vsummary 库内使用的 ``LinkedSeries``。
    """
    return LinkedSeries(
        series_id=f"chaoxing-{_safe_key(course_key)}",
        title=course_title,
        cover_url="",
        source_url=f"chaoxing://course/{course_key}",
        videos=videos,
    )


def _raise_if_import_cancelled(progress: ProgressReporter | None) -> None:
    """检查导入取消信号，已取消则抛出 ``ChaoxingImportCancelled``。

    Args:
        progress: 进度报告器（可为 ``None``）；不为 ``None`` 时检查
            ``is_cancel_requested()``。

    Raises:
        ChaoxingImportCancelled: 用户取消导入。
    """
    if progress is not None and progress.is_cancel_requested():
        raise ChaoxingImportCancelled("超星课程导入已取消")


def _safe_key(value: str) -> str:
    """将任意字符串转为合法的键（仅保留字母数字、连字符和下划线）。

    Args:
        value: 原始字符串。

    Returns:
        清理后的键；完全为空时返回 ``"item"``。
    """
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return normalized or "item"


def _text(value: object) -> str:
    """安全地将值转为去空白后的字符串。

    Args:
        value: 待转换的值。

    Returns:
        去空白后的字符串（非 str 先 ``str()`` 再 strip）。
    """
    return value.strip() if isinstance(value, str) else str(value or "").strip()


def _positive_int(value: object) -> int:
    """安全地将值转为正整数；bool 和 <=0 返回 0。

    Args:
        value: 待转换的值。

    Returns:
        正整数或 0。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return 0


def _is_chaoxing_init_cancelled(error: BaseException) -> bool:
    """判断异常是否是 chaoxing-downloader 的 ``InitCancelled``。

    不直接 import 类名以避免循环依赖；通过类名字符串判断。

    Args:
        error: 捕获的异常。

    Returns:
        若是 ``InitCancelled`` 则返回 ``True``。
    """
    return error.__class__.__name__ == "InitCancelled"


def _validate_downloader_init_signature(downloader_cls) -> None:
    """校验 chaoxing-downloader 的版本是否 >= 0.1.3（通过 ``init`` 签名判断）。

    Args:
        downloader_cls: ``ChaoxingDownloader`` 类引用。

    Raises:
        RuntimeError: 版本过旧，缺少必要的参数。
    """
    try:
        parameters = inspect.signature(downloader_cls.init).parameters
    except (AttributeError, TypeError, ValueError) as error:
        raise RuntimeError("当前 Python 环境缺少 chaoxing-downloader 0.1.3，请先安装项目依赖。") from error
    if "collect_impl" not in parameters:
        raise RuntimeError("当前 Python 环境缺少 chaoxing-downloader 0.1.3，请先安装项目依赖。")


def _is_unsupported_chapter(error: BaseException) -> bool:
    """判断异常是否为「非视频章节」（应跳过而非报错）。

    Args:
        error: 捕获的异常。

    Returns:
        若是 ``UnsupportedChapterError`` 或消息中含"未解析到课程章节"则返回 ``True``。
    """
    return error.__class__.__name__ == "UnsupportedChapterError" or "未解析到课程章节" in str(error)


def _call_chaoxing(call):
    """包装 chaoxing-downloader 调用，统一处理反爬检测。

    若异常中包含 ``antispiderShowVerify.ac`` URL，则拼接中文提示后重新抛出；
    其他异常原样上抛。

    Args:
        call: 实际调用 lambda。
    """
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
    """判断异常是否由超星反爬验证触发。

    Args:
        error: 捕获的异常。

    Returns:
        若异常响应 URL 含 ``antispiderShowVerify.ac`` 则返回 ``True``。
    """
    return bool(_chaoxing_antispider_url(error))


def _chaoxing_antispider_url(error: BaseException) -> str:
    """从异常对象中提取超星反爬验证页面的 URL。

    Args:
        error: 捕获的异常。

    Returns:
        反爬验证页的 URL；若未命中则返回空字符串。
    """
    response = getattr(error, "response", None)
    url = str(getattr(response, "url", ""))
    return url if "antispiderShowVerify.ac" in url else ""
