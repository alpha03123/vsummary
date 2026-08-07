"""从 Bilibili 与本地媒体读取可直接使用的中文字幕转写。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import subprocess

import srt

from backend.shared.bilibili_ytdlp import (
    load_bilibili_headers,
    resolve_yt_dlp_proxy,
    write_bilibili_cookies_file,
)
from backend.video_summary.domain.models import ManualTranscriptInput, Transcript, TranscriptSegment
from backend.video_summary.generation.cancellation import GenerationCancellationContext, ProcessHandle

LOGGER = logging.getLogger(__name__)

_BVID_PATTERN = re.compile(r"(BV[0-9A-Za-z]{10})", re.IGNORECASE)
_PAGE_PATTERN = re.compile(r"_p(?P<page>[1-9][0-9]*)$", re.IGNORECASE)
_TEXT_SUBTITLE_CODECS = frozenset({"ass", "mov_text", "srt", "ssa", "subrip", "webvtt"})
_LOCAL_CHINESE_LANGUAGE_PRIORITY = ("zh-hans", "zh-cn", "zh", "zho", "chi", "cmn")
_BILIBILI_CHINESE_LANGUAGE_PRIORITY = ("zh-Hans", "zh-CN", "zh", "ai-zh")


class SubtitleTranscriptProvider:
    """按 Bilibili、内嵌字幕的顺序尝试获得中文字幕转写。"""

    cache_identity = "subtitle-transcript-v1"

    def load(
        self,
        video_path: Path,
        staging_dir: Path,
        cancellation: GenerationCancellationContext | None = None,
    ) -> Transcript | None:
        """返回可用中文字幕；找不到时返回 ``None`` 以让调用方走 ASR。"""
        bilibili = _load_bilibili_subtitle(video_path, cancellation)
        if bilibili is not None:
            return bilibili
        return _load_embedded_subtitle(video_path, staging_dir / "subtitle.srt", cancellation)


class ManualSrtTranscriptProvider:
    """读取当前视频已提交的人工 SRT。"""

    def load(self, output_dir: Path) -> ManualTranscriptInput | None:
        path = output_dir / "transcript.manual.srt"
        if not path.is_file():
            return None
        raw_srt = path.read_text(encoding="utf-8-sig")
        return ManualTranscriptInput(
            transcript=parse_srt_transcript(raw_srt),
            raw_srt=raw_srt,
            filename=path.name,
        )


class _SilentYtDlpLogger:
    """阻止 listsubtitles 将轨道表直接写入后端 stdout。"""

    def debug(self, message: str) -> None:
        LOGGER.debug("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        LOGGER.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        LOGGER.warning("yt-dlp: %s", message)


def _load_bilibili_subtitle(
    video_path: Path,
    cancellation: GenerationCancellationContext | None = None,
) -> Transcript | None:
    bvid_match = _BVID_PATTERN.search(video_path.stem)
    if bvid_match is None:
        return None
    _raise_if_cancelled(cancellation)
    bvid = bvid_match.group(1)
    page_match = _PAGE_PATTERN.search(video_path.stem)
    page = int(page_match.group("page")) if page_match is not None else 1
    url = f"https://www.bilibili.com/video/{bvid}" + (f"?p={page}" if page > 1 else "")
    headers = load_bilibili_headers(bvid)
    cookie_file = write_bilibili_cookies_file(headers.pop("Cookie", ""))
    options: dict[str, object] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "listsubtitles": True,
        "socket_timeout": 20,
        "http_headers": headers,
        "logger": _SilentYtDlpLogger(),
    }
    proxy = resolve_yt_dlp_proxy()
    if proxy is not None:
        options["proxy"] = proxy
    if cookie_file is not None:
        options["cookiefile"] = str(cookie_file)
    try:
        from yt_dlp import YoutubeDL

        with YoutubeDL(options) as ydl:
            ydl.to_screen = _discard_ytdlp_screen_output
            ydl.to_stdout = _discard_ytdlp_screen_output
            info = ydl.extract_info(url, download=False)
        _raise_if_cancelled(cancellation)
        if not isinstance(info, dict):
            return None
        subtitles = info.get("subtitles")
        if not isinstance(subtitles, dict):
            return None
        for language in _BILIBILI_CHINESE_LANGUAGE_PRIORITY:
            entries = subtitles.get(language)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("ext") != "srt":
                    continue
                data = entry.get("data")
                if isinstance(data, str) and data.strip():
                    return parse_srt_transcript(data)
        return None
    except InterruptedError:
        raise
    except Exception:
        _raise_if_cancelled(cancellation)
        LOGGER.warning("Bilibili 中文字幕读取失败，回退 ASR：%s", bvid, exc_info=True)
        return None
    finally:
        if cookie_file is not None:
            cookie_file.unlink(missing_ok=True)


def _load_embedded_subtitle(
    video_path: Path,
    output_path: Path,
    cancellation: GenerationCancellationContext | None = None,
) -> Transcript | None:
    try:
        stream_index = _find_chinese_text_subtitle_stream(video_path, cancellation)
        if stream_index is None:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _run_subprocess(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-i",
                str(video_path),
                "-map",
                f"0:{stream_index}",
                str(output_path),
            ],
            cancellation,
        )
        return parse_srt_transcript(output_path.read_text(encoding="utf-8-sig"))
    except InterruptedError:
        raise
    except Exception:
        _raise_if_cancelled(cancellation)
        LOGGER.warning("内嵌中文字幕读取失败，回退 ASR：%s", video_path, exc_info=True)
        return None
    finally:
        output_path.unlink(missing_ok=True)


def _find_chinese_text_subtitle_stream(
    video_path: Path,
    cancellation: GenerationCancellationContext | None = None,
) -> int | None:
    result = _run_subprocess(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video_path)],
        cancellation,
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return None
    candidates: list[tuple[int, int]] = []
    for stream in streams:
        if not isinstance(stream, dict) or stream.get("codec_type") != "subtitle":
            continue
        codec = str(stream.get("codec_name", "")).lower()
        tags = stream.get("tags")
        language = str(tags.get("language", "")).lower() if isinstance(tags, dict) else ""
        if codec not in _TEXT_SUBTITLE_CODECS or language not in _LOCAL_CHINESE_LANGUAGE_PRIORITY:
            continue
        index = stream.get("index")
        if not isinstance(index, int):
            continue
        candidates.append((_LOCAL_CHINESE_LANGUAGE_PRIORITY.index(language), index))
    return min(candidates)[1] if candidates else None


def _run_subprocess(
    command: list[str],
    cancellation: GenerationCancellationContext | None = None,
) -> subprocess.CompletedProcess[str]:
    _raise_if_cancelled(cancellation)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    handle = ProcessHandle(_proc=process)
    if cancellation is not None:
        cancellation.register(handle)
        if cancellation.cancel_requested:
            process.kill()
    try:
        stdout, stderr = process.communicate()
    finally:
        if cancellation is not None:
            cancellation.unregister(handle)
    _raise_if_cancelled(cancellation)
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def parse_srt_transcript(content: str) -> Transcript:
    """将非空 SRT 文本转换为按时间排序的中文 ``Transcript``。"""
    subtitles = list(srt.parse(content))
    segments = [
        TranscriptSegment(
            start_seconds=item.start.total_seconds(),
            end_seconds=item.end.total_seconds(),
            text=item.content.strip(),
        )
        for item in subtitles
        if item.content.strip() and item.end > item.start
    ]
    if not segments:
        raise ValueError("字幕中没有有效时间片段。")
    return Transcript(language="zh", segments=segments)


def _discard_ytdlp_screen_output(*args: object, **kwargs: object) -> None:
    """字幕枚举是内部步骤，不向后端 stdout 输出 yt-dlp 的轨道表。"""


def _raise_if_cancelled(cancellation: GenerationCancellationContext | None) -> None:
    if cancellation is not None and cancellation.cancel_requested:
        raise InterruptedError("任务已取消")
