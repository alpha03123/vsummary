from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path
from typing import Protocol


class ProgressReporter(Protocol):
    def update(self, stage: str, progress: float | None = None, detail: str | None = None) -> None: ...
    def completed(self, detail: str | None = None) -> None: ...
    def failed(self, message: str) -> None: ...
    def cancelled(self, detail: str | None = None) -> None: ...


class BilibiliDownloader:
    _PROGRESS_RE = re.compile(r"\[download\]\s+([\d.]+)%")

    def download(self, bvid: str, page: int, dest_dir: Path, reporter: ProgressReporter) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://www.bilibili.com/video/{bvid}"
        if page > 1:
            url = f"{url}?p={page}"

        stem = bvid if page == 1 else f"{bvid}_p{page}"
        output_template = str(dest_dir / f"{stem}.%(ext)s")
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--merge-output-format",
            "mp4",
            "--output",
            output_template,
            "--newline",
            "--no-part",
            url,
        ]

        reporter.update("download", 0.0, "开始下载")
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            last_percent = -1.0
            assert process.stdout is not None
            for line in process.stdout:
                match = self._PROGRESS_RE.search(line.rstrip())
                if not match:
                    continue
                percent = float(match.group(1))
                if percent == last_percent:
                    continue
                last_percent = percent
                reporter.update("download", percent, f"下载中 {percent:.1f}%")

            process.wait()
            if process.returncode != 0:
                raise RuntimeError(f"yt-dlp 退出码 {process.returncode}")
        except Exception as exc:
            reporter.failed(str(exc))
            raise

        candidates = list(dest_dir.glob(f"{stem}.*"))
        if not candidates:
            error_message = f"yt-dlp 下载完成但未找到输出文件：{stem}.*"
            reporter.failed(error_message)
            raise RuntimeError(error_message)

        result = candidates[0]
        reporter.completed(f"下载完成：{result.name}")
        return result

    async def download_async(self, bvid: str, page: int, dest_dir: Path, reporter: ProgressReporter) -> Path:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.download, bvid, page, dest_dir, reporter)
