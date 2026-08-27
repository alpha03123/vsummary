"""基于 ffprobe / ffmpeg 的轻量媒体工具。

为 ASR 流程提供两件事：
- `probe_duration`：读出视频/音频的总时长（秒），用于转写进度比例；
- `extract_audio`：把任意媒体抽成 16kHz 单声道 WAV（whisper 推荐输入格式），
  并通过 `GenerationCancellationContext` 支持中途取消（终止 ffmpeg 子进程）。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from uuid import uuid4

from backend.video_summary.generation.cancellation import GenerationCancellationContext, ProcessHandle
from backend.video_summary.generation.ports import NoTranscribableAudioError, NoVideoFramesError


LOGGER = logging.getLogger(__name__)


class FfmpegMediaProcessor:
    """对 ffprobe / ffmpeg 命令行的薄封装，配合取消上下文一起使用。"""

    def probe_duration(self, video_path: Path) -> float:
        """调用 ffprobe 读取媒体时长。

        Args:
            video_path: 任意 ffprobe 可识别的媒体文件。

        Returns:
            总时长（秒，`float`）。

        Raises:
            subprocess.CalledProcessError: ffprobe 命令失败。
            ValueError: ffprobe 输出无法解析为浮点。
        """
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return float(result.stdout.strip())

    def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        cancellation: GenerationCancellationContext | None = None,
    ) -> Path:
        """把媒体抽成 16kHz 单声道 PCM s16le WAV（whisper 推荐输入）。

        关键行为：
        - 通过 `-y` 强制覆盖目标输出；
        - 关闭 stdout/stderr，避免子进程输出阻塞管道；
        - 若提供 `cancellation`，会注册 `ProcessHandle` 使取消时自动 `terminate`
          子进程；取消成功后即便 returncode 非 0 也不会抛 `CalledProcessError`。

        Args:
            video_path: 输入媒体路径。
            audio_path: 目标 WAV 路径，父目录会自动创建。
            cancellation: 可选的取消上下文；为 `None` 时同步等待 ffmpeg 完成。

        Returns:
            写入后的 `audio_path`。

        Raises:
            NoTranscribableAudioError: 输入媒体不含音频流。
            subprocess.CalledProcessError: ffmpeg 退出码非 0 且非取消导致时抛出。
        """
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._has_audio_stream(video_path):
            raise NoTranscribableAudioError(f"媒体文件不含音频流：{video_path.name}")
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ]
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        stderr = b""
        if cancellation is not None:
            handle = ProcessHandle(_proc=proc)
            cancellation.register(handle)
            try:
                _, stderr = proc.communicate()
            finally:
                cancellation.unregister(handle)
        else:
            _, stderr = proc.communicate()

        if proc.returncode != 0 and not (cancellation is not None and cancellation.cancel_requested):
            _raise_ffmpeg_failure(
                operation="audio extraction",
                command=command,
                returncode=proc.returncode,
                stderr=stderr,
                video_path=video_path,
            )
        return audio_path

    def extract_frame(
        self,
        video_path: Path,
        timestamp_seconds: float,
        output_path: Path,
        cancellation: GenerationCancellationContext | None = None,
    ) -> Path:
        """用 ffmpeg 在指定时间点抽取 JPEG 图片。"""
        if timestamp_seconds < 0:
            raise ValueError("截图时间不能小于 0")
        if not self._has_video_stream(video_path):
            raise NoVideoFramesError(f"媒体不含可供截图的视频流：{video_path.name}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{timestamp_seconds:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-q:v",
            "3",
            str(output_path),
        ]
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        stderr = b""
        if cancellation is not None:
            handle = ProcessHandle(_proc=proc)
            cancellation.register(handle)
            try:
                _, stderr = proc.communicate()
            finally:
                cancellation.unregister(handle)
        else:
            _, stderr = proc.communicate()
        if proc.returncode != 0 and not (cancellation is not None and cancellation.cancel_requested):
            _raise_ffmpeg_failure(
                operation="frame extraction",
                command=command,
                returncode=proc.returncode,
                stderr=stderr,
                video_path=video_path,
                timestamp_seconds=timestamp_seconds,
            )
        if cancellation is not None and cancellation.cancel_requested:
            raise InterruptedError("生成已取消")
        if not output_path.is_file():
            raise RuntimeError(f"ffmpeg 未生成截图：{output_path.name}")
        return output_path

    def ensure_browser_playable_mp4(self, video_path: Path) -> Path:
        """将索引位于媒体数据之后的 MP4 无损重封装为可快速起播的文件。

        仅处理 MP4 家族容器；完整 ``moov`` 索引已经位于 ``mdat`` 前且不是
        碎片化 MP4 的文件直接返回，不重复读写。重封装成功后原子替换库内媒体
        副本，避免长期占用双份磁盘空间。
        """
        if video_path.suffix.lower() not in {".mp4", ".m4v", ".mov"} or _is_browser_playable_mp4(video_path):
            return video_path

        temporary_path = video_path.with_name(
            f".{video_path.stem}.{uuid4().hex}.faststart{video_path.suffix}"
        )
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(video_path),
            "-map",
            "0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary_path),
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
            )
            if result.returncode != 0:
                _raise_ffmpeg_failure(
                    operation="browser playback preparation",
                    command=command,
                    returncode=result.returncode,
                    stderr=result.stderr,
                    video_path=video_path,
                )
            if not temporary_path.is_file():
                raise RuntimeError(f"ffmpeg 未生成浏览器播放文件：{temporary_path.name}")
            temporary_path.replace(video_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return video_path

    @staticmethod
    def _has_audio_stream(video_path: Path) -> bool:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=index",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return bool(result.stdout.strip())

    @staticmethod
    def _has_video_stream(video_path: Path) -> bool:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=index",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return bool(result.stdout.strip())


def _raise_ffmpeg_failure(
    *,
    operation: str,
    command: list[str],
    returncode: int,
    stderr: bytes,
    video_path: Path,
    timestamp_seconds: float | None = None,
) -> None:
    """记录 FFmpeg 原始失败证据后立即抛出原始 ``CalledProcessError``。"""
    error = subprocess.CalledProcessError(returncode, command, stderr=stderr)
    try:
        raise error
    except subprocess.CalledProcessError:
        LOGGER.exception(
            "ffmpeg %s failed",
            operation,
            extra={
                "event": "ffmpeg_failed",
                "command": command,
                "returncode": returncode,
                "stderr": stderr.decode("utf-8", errors="replace"),
                "video_path": video_path,
                "timestamp_seconds": timestamp_seconds,
            },
        )
        raise


def _is_browser_playable_mp4(video_path: Path) -> bool:
    """判断 MP4 是否有位于媒体数据前的完整索引且不是碎片化容器。"""
    file_size = video_path.stat().st_size
    offset = 0
    has_front_moov = False
    with video_path.open("rb") as handle:
        while offset + 8 <= file_size:
            handle.seek(offset)
            header = handle.read(8)
            box_size = int.from_bytes(header[:4], "big")
            box_type = header[4:]
            header_size = 8
            if box_size == 1:
                extended_size = handle.read(8)
                if len(extended_size) != 8:
                    return False
                box_size = int.from_bytes(extended_size, "big")
                header_size = 16
            elif box_size == 0:
                box_size = file_size - offset
            if box_size < header_size or offset + box_size > file_size:
                return False
            if box_type == b"moof":
                return False
            if box_type == b"moov":
                has_front_moov = True
            if box_type == b"mdat":
                return has_front_moov
            offset += box_size
    return has_front_moov
