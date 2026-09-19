"""基于 LiteLLM 的视频 AI 笔记生成器。"""

from __future__ import annotations

from pathlib import Path
import re
from threading import Lock
from typing import Literal

from pydantic import BaseModel, Field

from backend.agent_graph.prompts.notes import build_ai_note_prompt
from backend.agent.schemas.action_plan import CitationReference, CitationSlot
from backend.shared.llm import LiteLLMCompletionGateway, build_multimodal_user_content
from backend.shared.llm.usage import LlmUsageCategory, LlmUsageRecorder
from backend.video_summary.infrastructure.config.settings import ensure_settings_file, load_settings
from backend.video_summary.infrastructure.video_summary_runtime import build_litellm_completion_gateway
from backend.video_summary.library.models import (
    GeneratedVideoAiNoteDTO,
    AiSummaryVisualEvidenceDTO,
    VideoAiNoteVisualContextDTO,
    VideoSummaryDTO,
    VideoTranscriptDTO,
)


# 笔记属于创作型任务：温度略高于 0，避免模型挑最保守的写法导致句式死板、篇幅偏短。
NOTE_TEMPERATURE = 0.3


class AiSummaryEvidencePayload(BaseModel):
    timestamp_seconds: float
    text: str = Field(min_length=1)


class AiSummaryCitationPayload(BaseModel):
    citation_id: int = Field(ge=1, le=20)
    source_type: Literal["transcript", "visual"]
    timestamp_seconds: float = Field(ge=0)


class AiSummaryPayload(BaseModel):
    markdown: str = Field(min_length=1)
    visual_evidence: list[AiSummaryEvidencePayload] = Field(default_factory=list)
    citations: list[AiSummaryCitationPayload] = Field(min_length=1, max_length=20)


class LiteLLMNoteGenerator:
    """把已有视频转写整理为一篇 Markdown 笔记。"""

    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    def run_ai_summary(
        self,
        *,
        transcript: VideoTranscriptDTO,
        summary: VideoSummaryDTO | None,
        visual_context: VideoAiNoteVisualContextDTO,
        template: str,
        multimodal_enabled: bool,
        note_visual_mode: str,
        note_max_images: int,
        note_image_min_gap_seconds: float,
    ) -> GeneratedVideoAiNoteDTO:
        transcript_text = "\n".join(
            f"[{segment.start_seconds:.3f}-{segment.end_seconds:.3f}] {segment.text.strip()}"
            for segment in transcript.segments
            if segment.text.strip()
        )
        if not transcript_text:
            raise ValueError("视频转写为空，无法生成 AI 概括。")
        prompt = build_ai_note_prompt(
            title=transcript.title,
            transcript_text=transcript_text,
            template=template,
            summary_text=_extract_summary_text(summary),
            outline_text=_build_outline_text(summary),
            visual_context=(
                visual_context if multimodal_enabled else VideoAiNoteVisualContextDTO(frames=[])
            ),
            note_visual_mode=note_visual_mode,
        ) + (
            "\n额外输出要求：返回 JSON 对象，包含 markdown、visual_evidence 与 citations。"
            "markdown 是最终 AI 概括 Markdown；visual_evidence 每项含 timestamp_seconds 和 text。"
            "仅记录确实能从随附九宫格图确认的画面事实；timestamp_seconds 必须使用给出的真实帧时间。"
            "citations 至少提供 3 条、最多 20 条，只为需要追溯的关键事实、步骤、数字、直接表述或画面描述建立，避免每一句都引用。"
            "在对应正文句末写 [citation_id]；citation_id 必须从 1 连续编号且只出现一次。"
            "source_type=transcript 时 timestamp_seconds 必须精确使用某行转写方括号中的 start 秒数；"
            "source_type=visual 时 timestamp_seconds 必须使用 visual_evidence 中已返回的真实帧时间。"
        )
        message_content = (
            build_multimodal_user_content(text=prompt, image_paths=[frame.image_path for frame in visual_context.frames])
            if multimodal_enabled and visual_context.frames
            else prompt
        )
        allowed_timestamps = tuple(visual_context.evidence_timestamps)
        for attempt in range(2):
            payload = self._gateway.complete_structured(
                [{"role": "user", "content": message_content}],
                response_model=AiSummaryPayload,
                temperature=NOTE_TEMPERATURE,
            )
            try:
                return _to_generated_note(
                    payload=payload,
                    transcript=transcript,
                    allowed_timestamps=allowed_timestamps,
                    note_visual_mode=note_visual_mode,
                    note_max_images=note_max_images,
                    note_image_min_gap_seconds=note_image_min_gap_seconds,
                )
            except ValueError:
                if attempt:
                    raise
                message_content = _citation_repair_instruction(message_content)
        raise AssertionError("AI summary validation loop must return or raise.")


def _citation_repair_instruction(message_content):
    instruction = (
        "\n重试要求：上一次响应的引用契约无效。请重新生成完整 JSON；"
        "markdown 中出现的所有 [数字] 标记集合必须与 citations 的 citation_id 集合完全相同，"
        "每个 citation_id 必须连续、只出现一次，且不得出现未声明的数字标记。"
    )
    if isinstance(message_content, str):
        return message_content + instruction
    if isinstance(message_content, list):
        return [*message_content, {"type": "text", "text": instruction.strip()}]
    raise TypeError("AI summary message content must be text or multimodal content parts.")


def _to_generated_note(
    *,
    payload: AiSummaryPayload,
    transcript: VideoTranscriptDTO,
    allowed_timestamps: tuple[float, ...],
    note_visual_mode: str,
    note_max_images: int,
    note_image_min_gap_seconds: float,
) -> GeneratedVideoAiNoteDTO:
    evidence: list[AiSummaryVisualEvidenceDTO] = []
    seen: set[float] = set()
    for item in payload.visual_evidence:
        timestamp = _resolve_visual_evidence_timestamp(item.timestamp_seconds, allowed_timestamps)
        if timestamp is None:
            raise ValueError("AI 概括视觉证据引用了未提供的帧时间。")
        if timestamp in seen:
            raise ValueError("同一视频帧只能有一条 AI 概括视觉证据。")
        seen.add(timestamp)
        evidence.append(AiSummaryVisualEvidenceDTO(timestamp_seconds=timestamp, text=item.text.strip()))
    citations = _build_ai_summary_citations(
        markdown=payload.markdown,
        citations=payload.citations,
        transcript=transcript,
        visual_evidence=evidence,
    )
    return GeneratedVideoAiNoteDTO(
        content=payload.markdown.strip(),
        note_visual_mode=note_visual_mode,
        note_max_images=note_max_images,
        note_image_min_gap_seconds=note_image_min_gap_seconds,
        visual_evidence=tuple(evidence),
        citations=tuple(citations),
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

    def run_ai_summary(
        self,
        *,
        transcript: VideoTranscriptDTO,
        summary: VideoSummaryDTO | None,
        visual_context: VideoAiNoteVisualContextDTO,
        template: str,
    ) -> GeneratedVideoAiNoteDTO:
        generator = self._get_generator()
        settings = load_settings(config_path=self._config_path, root_dir=self._root_dir)
        return generator.run_ai_summary(
            transcript=transcript,
            summary=summary,
            visual_context=visual_context,
            template=template,
            multimodal_enabled=settings.generation.ai_summary_multimodal_enabled,
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


def _resolve_visual_evidence_timestamp(value: float, allowed: tuple[float, ...]) -> float | None:
    """把九宫格显示到秒的模型输出回填为真实候选帧时间。"""
    if not allowed:
        return None
    candidate = min(allowed, key=lambda timestamp: abs(timestamp - value))
    return candidate if abs(candidate - value) <= 1.0 else None


def _build_ai_summary_citations(
    *,
    markdown: str,
    citations: list[AiSummaryCitationPayload],
    transcript: VideoTranscriptDTO,
    visual_evidence: list[AiSummaryVisualEvidenceDTO],
) -> list[CitationReference]:
    marker_ids = {int(value) for value in re.findall(r"\[(\d+)\]", markdown)}
    declared_ids = {item.citation_id for item in citations}
    if marker_ids != declared_ids:
        raise ValueError("AI 概括正文中的引用角标必须与 citations 一一对应。")
    if len(citations) != len(declared_ids):
        raise ValueError("AI 概括引用 ID 不能重复。")
    if declared_ids != set(range(1, len(citations) + 1)):
        raise ValueError("AI 概括引用 ID 必须从 1 连续编号。")

    result: list[CitationReference] = []
    for item in sorted(citations, key=lambda citation: citation.citation_id):
        citation_id = str(item.citation_id)
        if item.source_type == "transcript":
            segment = _resolve_transcript_segment(item.timestamp_seconds, transcript)
            if segment is None:
                raise ValueError("AI 概括引用了未提供的转写时间。")
            result.append(
                CitationReference(
                    id=citation_id,
                    label=transcript.title,
                    source_type="transcript",
                    search_scope="transcript",
                    slots=[
                        CitationSlot(
                            slot=1,
                            target_type="video",
                            video_id=transcript.video_id,
                            video_title=transcript.title,
                            start_seconds=segment.start_seconds,
                            end_seconds=segment.end_seconds,
                        ),
                        CitationSlot(
                            slot=2,
                            target_type="transcript",
                            video_id=transcript.video_id,
                            video_title=transcript.title,
                            start_seconds=segment.start_seconds,
                            end_seconds=segment.end_seconds,
                            text=segment.text,
                        ),
                    ],
                )
            )
            continue
        evidence = _resolve_visual_evidence(item.timestamp_seconds, visual_evidence)
        if evidence is None:
            raise ValueError("AI 概括引用了未验证的视觉证据时间。")
        result.append(
            CitationReference(
                id=citation_id,
                label=transcript.title,
                source_type="visual",
                search_scope="visual",
                slots=[
                    CitationSlot(
                        slot=1,
                        target_type="video",
                        video_id=transcript.video_id,
                        video_title=transcript.title,
                        start_seconds=evidence.timestamp_seconds,
                        end_seconds=evidence.timestamp_seconds,
                        text=evidence.text,
                    )
                ],
            )
        )
    return result


def _resolve_transcript_segment(timestamp: float, transcript: VideoTranscriptDTO):
    if not transcript.segments:
        return None
    candidate = min(transcript.segments, key=lambda segment: abs(segment.start_seconds - timestamp))
    return candidate if abs(candidate.start_seconds - timestamp) <= 0.01 else None


def _resolve_visual_evidence(timestamp: float, evidence: list[AiSummaryVisualEvidenceDTO]) -> AiSummaryVisualEvidenceDTO | None:
    if not evidence:
        return None
    candidate = min(evidence, key=lambda item: abs(item.timestamp_seconds - timestamp))
    return candidate if abs(candidate.timestamp_seconds - timestamp) <= 1.0 else None
