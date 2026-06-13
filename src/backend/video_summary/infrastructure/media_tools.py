from __future__ import annotations

import subprocess
from pathlib import Path

from backend.video_summary.generation.cancellation import GenerationCancellationContext, ProcessHandle


class FfmpegMediaProcessor:
    def probe_duration(self, video_path: Path) -> float:
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
