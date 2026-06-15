"""基于 ffprobe / ffmpeg 的轻量媒体工具。

为 ASR 流程提供两件事：
- `probe_duration`：读出视频/音频的总时长（秒），用于转写进度比例；
- `extract_audio`：把任意媒体抽成 16kHz 单声道 WAV（whisper 推荐输入格式），
  并通过 `GenerationCancellationContext` 支持中途取消（终止 ffmpeg 子进程）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from backend.video_summary.generation.cancellation import GenerationCancellationContext, ProcessHandle


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
            subprocess.CalledProcessError: ffmpeg 退出码非 0 且非取消导致时抛出。
        """
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [
                "ffmpeg",
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
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if cancellation is not None:
            handle = ProcessHandle(_proc=proc)
            cancellation.register(handle)
            try:
                proc.wait()
            finally:
                cancellation.unregister(handle)
        else:
            proc.wait()

        if proc.returncode != 0 and not (cancellation is not None and cancellation.cancel_requested):
            raise subprocess.CalledProcessError(proc.returncode, "ffmpeg")
        return audio_path
