"""通过 ``whisper-cli`` 调用 whisper.cpp 并转换为领域转写结果。"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable

from backend.video_summary.domain.models import Transcript, TranscriptSegment


class WhisperCppTranscriber:
    """调用已安装的 whisper.cpp CLI，读取其 JSON 输出。"""

    def __init__(self, *, binary_path: str, model_path: Path, language: str = "auto") -> None:
        self._binary_path = _resolve_binary(binary_path)
        self._model_path = model_path
        self._language = language
        self.cache_identity = "|".join(
            [type(self).__module__, type(self).__qualname__, str(self._binary_path), str(model_path), language]
        )

    def transcribe(
        self,
        audio_path: Path,
        output_stem: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        if not self._model_path.is_file():
            raise RuntimeError(f"whisper.cpp 模型文件不存在：{self._model_path}")

        output_stem.parent.mkdir(parents=True, exist_ok=True)
        output_base = output_stem.parent / f"{output_stem.name}.whisper-cpp"
        output_json = Path(f"{output_base}.json")
        output_json.unlink(missing_ok=True)
        command = [
            str(self._binary_path),
            "-m",
            str(self._model_path),
            "-f",
            str(audio_path),
            "-oj",
            "-of",
            str(output_base),
        ]
        if self._language != "auto":
            command.extend(["-l", self._language])
        if on_progress is not None:
            on_progress(0.0)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
            raise RuntimeError(f"whisper.cpp 转写失败：{detail}")
        if not output_json.is_file():
            raise RuntimeError(f"whisper.cpp 未生成 JSON 转写结果：{output_json}")

        payload = json.loads(output_json.read_text(encoding="utf-8"))
        segments = [
            TranscriptSegment(
                start_seconds=float(item["offsets"]["from"]) / 1000,
                end_seconds=float(item["offsets"]["to"]) / 1000,
                text=str(item.get("text", "")).strip(),
            )
            for item in payload.get("transcription", [])
            if isinstance(item, dict)
            and isinstance(item.get("offsets"), dict)
            and str(item.get("text", "")).strip()
        ]
        if on_progress is not None:
            on_progress(1.0)
        result = payload.get("result")
        detected_language = result.get("language") if isinstance(result, dict) else None
        return Transcript(language=str(detected_language or self._language), segments=segments)


def _resolve_binary(binary_path: str) -> Path:
    candidate = Path(binary_path).expanduser()
    if candidate.parent != Path("."):
        if candidate.is_file():
            return candidate.resolve()
    else:
        resolved = shutil.which(binary_path)
        if resolved:
            return Path(resolved)
    raise RuntimeError(
        f"未找到 whisper.cpp 可执行文件：{binary_path}。请设置 asr.whisper_cpp.binary_path。"
    )
