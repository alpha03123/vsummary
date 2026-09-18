"""基于 LiteLLM 的视频 AI 笔记生成器。"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.agent_graph.prompts.notes import build_ai_note_prompt
from backend.shared.llm import LiteLLMCompletionGateway, build_multimodal_user_content
from backend.shared.llm.usage import LlmUsageCategory, LlmUsageRecorder
from backend.video_summary.infrastructure.config.settings import ensure_settings_file, load_settings
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway
from backend.video_summary.library.models import (
    GeneratedVideoAiNoteDTO,
    VideoAiNoteVisualContextDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
)


# 笔记属于创作型任务：温度略高于 0，避免模型挑最保守的写法导致句式死板、篇幅偏短。
NOTE_TEMPERATURE = 0.3


class LiteLLMNoteGenerator:
    """把已有视频转写整理为一篇 Markdown 笔记。"""

    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    def run(
        self,
        *,
        transcript: VideoTranscriptDTO,
        summary: VideoSummaryDTO | None,
        visual_context: VideoAiNoteVisualContextDTO,
        template: str,
        visual_input: str,
        note_visual_mode: str,
        note_max_images: int,
        note_image_min_gap_seconds: float,
    ) -> GeneratedVideoAiNoteDTO:
        transcript_text = "\n".join(
            f"{_format_timestamp(segment.start_seconds)} - {segment.text.strip()}"
            for segment in transcript.segments
            if segment.text.strip()
        )
        if not transcript_text:
            raise ValueError("视频转写为空，无法生成 AI 笔记。")
        summary_text = _extract_summary_text(summary)
        outline_text = _build_outline_text(summary)
        prompt = build_ai_note_prompt(
                title=transcript.title,
                transcript_text=transcript_text,
                template=template,
                summary_text=summary_text,
                outline_text=outline_text,
                visual_context=(
                    VideoAiNoteVisualContextDTO(frames=[], evidence_text=visual_context.evidence_text)
                    if visual_input == "evidence"
                    else VideoAiNoteVisualContextDTO(frames=[], evidence_text="")
                    if visual_input == "none"
                    else visual_context
                ),
                note_visual_mode=note_visual_mode,
            )
        content = self._gateway.complete_text(
            [{"role": "user", "content": (
                build_multimodal_user_content(text=prompt, image_paths=[frame.image_path for frame in visual_context.frames])
                if visual_input == "frames" and visual_context.frames
                else prompt
            )}],
            temperature=NOTE_TEMPERATURE,
        )
        if not content.strip():
            raise RuntimeError("模型未返回 AI 笔记。")
        return GeneratedVideoAiNoteDTO(
            content=content.strip(),
            note_visual_mode=note_visual_mode,
            note_max_images=note_max_images,
            note_image_min_gap_seconds=note_image_min_gap_seconds,
        )


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

    def run(
        self,
        *,
        transcript: VideoTranscriptDTO,
        summary: VideoSummaryDTO | None,
        visual_context: VideoAiNoteVisualContextDTO,
        template: str,
    ) -> GeneratedVideoAiNoteDTO:
        generator = self._get_generator()
        settings = load_settings(config_path=self._config_path, root_dir=self._root_dir)
        return generator.run(
            transcript=transcript,
            summary=summary,
            visual_context=visual_context,
            template=template,
            visual_input=settings.generation.note_visual_input,
            note_visual_mode=settings.generation.note_visual_mode,
            note_max_images=settings.generation.note_max_images,
            note_image_min_gap_seconds=settings.generation.note_image_min_gap_seconds,
        )

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


def _extract_summary_text(summary: VideoSummaryDTO | None) -> str:
    """取出概况里的核心问题描述。

    只在取值确实是字符串时返回，避免把缺失字段的 `None` 变成 `"None"` 注入提示词。
    """
    if summary is None:
        return ""
    value = summary.summary.get("core_problem")
    return str(value).strip() if isinstance(value, str) else ""


def _build_outline_text(summary: VideoSummaryDTO | None) -> str:
    """把概况的章节标题整理成参考大纲。

    笔记生成时参考该大纲，可以让章节划分与原片既有结构保持一致，
    而不是完全由模型自行切分。
    """
    if summary is None:
        return ""
    chapters = summary.summary.get("chapters")
    if not isinstance(chapters, list):
        return ""
    lines: list[str] = []
    for index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            continue
        chapter_title = str(chapter.get("title") or "").strip()
        if not chapter_title:
            continue
        lines.append(f"{index}. {chapter_title}")
    return "\n".join(lines)


def _format_timestamp(seconds: float) -> str:
    whole_seconds = max(0, int(seconds))
    minutes, seconds_part = divmod(whole_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}" if hours else f"{minutes:02d}:{seconds_part:02d}"
