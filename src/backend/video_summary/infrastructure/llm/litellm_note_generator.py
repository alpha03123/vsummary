"""基于 LiteLLM 的视频 AI 笔记生成器。"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.agent_graph.prompts.notes import build_ai_note_prompt
from backend.shared.llm import LiteLLMCompletionGateway
from backend.shared.llm.usage import LlmUsageCategory, LlmUsageRecorder
from backend.video_summary.infrastructure.config.settings import ensure_settings_file, load_settings
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway
from backend.video_summary.library.models import VideoSummaryDTO, VideoTranscriptDTO


class LiteLLMNoteGenerator:
    """把已有视频转写整理为一篇 Markdown 笔记。"""

    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    def run(self, *, transcript: VideoTranscriptDTO, summary: VideoSummaryDTO | None, template: str) -> str:
        transcript_text = "\n".join(
            f"{_format_timestamp(segment.start_seconds)} - {segment.text.strip()}"
            for segment in transcript.segments
            if segment.text.strip()
        )
        if not transcript_text:
            raise ValueError("视频转写为空，无法生成 AI 笔记。")
        summary_text = ""
        if summary is not None:
            summary_text = str(summary.summary.get("core_problem", "")).strip()
        content = self._gateway.complete_text(
            [{"role": "user", "content": build_ai_note_prompt(
                title=transcript.title,
                transcript_text=transcript_text,
                template=template,
                summary_text=summary_text,
            )}],
            temperature=0,
        )
        if not content.strip():
            raise RuntimeError("模型未返回 AI 笔记。")
        return content.strip()


class ConfiguredNoteGenerator:
    """按当前设置懒加载并复用 AI 笔记生成器。"""

    def __init__(self, root_dir: Path, usage_recorder: LlmUsageRecorder | None = None) -> None:
        self._root_dir = root_dir
        self._usage_recorder = usage_recorder
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._lock = Lock()
        self._signature: tuple[str, str] | None = None
        self._generator: LiteLLMNoteGenerator | None = None

    def run(self, *, transcript: VideoTranscriptDTO, summary: VideoSummaryDTO | None, template: str) -> str:
        return self._get_generator().run(transcript=transcript, summary=summary, template=template)

    def _get_generator(self) -> LiteLLMNoteGenerator:
        ensure_settings_file(self._config_path)
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
        )
        with self._lock:
            if self._generator is None or signature != self._signature:
                settings = load_settings(config_path=self._config_path, root_dir=self._root_dir)
                self._generator = LiteLLMNoteGenerator(build_litellm_completion_gateway(
                    settings,
                    usage_recorder=self._usage_recorder,
                    usage_category=LlmUsageCategory.GENERATION if self._usage_recorder is not None else None,
                ))
                self._signature = signature
            return self._generator


def _format_timestamp(seconds: float) -> str:
    whole_seconds = max(0, int(seconds))
    minutes, seconds_part = divmod(whole_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}" if hours else f"{minutes:02d}:{seconds_part:02d}"
