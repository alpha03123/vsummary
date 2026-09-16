"""基于 LiteLLM 的视频截图视觉增强器。"""

from __future__ import annotations

import json

from backend.shared.llm import LiteLLMCompletionGateway, build_multimodal_user_content
from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation import MultimodalSummaryPayload, VisualEvidencePayload, render_markdown
from backend.video_summary.generation.cancellation import GenerationCancellationContext, cancellable_await
from backend.video_summary.generation.visuals import ExtractedChapterFrame


class LiteLLMVisualSummaryEnricher:
    """一次视觉模型调用同时生成最终概况与可检索逐帧描述。"""

    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    async def enrich(
        self,
        *,
        video: VideoAsset,
        transcript: Transcript,
        draft: SummaryDocument,
        frames: list[ExtractedChapterFrame],
        cancellation: GenerationCancellationContext | None = None,
    ) -> tuple[SummaryDocument, VisualEvidencePayload]:
        if not frames:
            return draft, VisualEvidencePayload()
        prompt = _build_visual_summary_prompt(video=video, transcript=transcript, draft=draft, frames=frames)
        message = {
            "role": "user",
            "content": build_multimodal_user_content(text=prompt, image_paths=[frame.path for frame in frames]),
        }
        request = self._gateway.acomplete_structured([message], response_model=MultimodalSummaryPayload)
        try:
            payload = await cancellable_await(request, cancellation) if cancellation else await request
        except Exception as error:
            raise RuntimeError("多模态视觉增强失败；请确认当前模型支持图片输入。") from error
        summary_data = payload.summary.model_dump(mode="json")
        _validate_enriched_summary(draft=draft, summary_data=summary_data)
        _restore_frame_references(summary_data=summary_data, frames=frames)
        evidence = _validate_visual_evidence(payload.visual_evidence, frames)
        return SummaryDocument(markdown=render_markdown(summary_data), summary_data=summary_data, mindmap_data=draft.mindmap_data), evidence


def _build_visual_summary_prompt(
    *,
    video: VideoAsset,
    transcript: Transcript,
    draft: SummaryDocument,
    frames: list[ExtractedChapterFrame],
) -> str:
    frame_context = []
    for frame in frames:
        nearby = _nearby_transcript(transcript, frame.timestamp_seconds)
        frame_context.append(
            {
                "chapter_id": frame.chapter_id,
                "timestamp_seconds": frame.timestamp_seconds,
                "image_filename": frame.image_filename,
                "nearby_transcript": nearby,
            }
        )
    return (
        "请结合视频转写、总结草稿和随附截图，输出结构化 JSON。\n"
        f"视频标题：{video.title}\n"
        f"视频时长（秒）：{video.duration_seconds}\n\n"
        "规则：\n"
        "1. summary 必须保留草稿所有章节的 id、顺序、start_seconds 和 end_seconds；只可补充由画面确认的信息。\n"
        "2. 不要根据常识编造；截图没有新增知识时可以不产生对应视觉证据。\n"
        "3. visual_evidence 的每条必须引用下方给出的 chapter_id、timestamp_seconds 和 image_filename，且 text 必须可脱离图片理解。\n"
        "4. 截图按下方 frame_context 顺序附在本消息之后。\n\n"
        f"总结草稿：\n{json.dumps(draft.summary_data, ensure_ascii=False, indent=2)}\n\n"
        f"frame_context：\n{json.dumps(frame_context, ensure_ascii=False, indent=2)}"
    )


def _nearby_transcript(transcript: Transcript, timestamp_seconds: float, window_seconds: float = 20.0) -> str:
    lines = [
        f"[{segment.start_seconds:.1f}-{segment.end_seconds:.1f}] {segment.text.strip()}"
        for segment in transcript.segments
        if segment.text.strip()
        and segment.end_seconds >= timestamp_seconds - window_seconds
        and segment.start_seconds <= timestamp_seconds + window_seconds
    ]
    return "\n".join(lines)


def _validate_enriched_summary(*, draft: SummaryDocument, summary_data: dict[str, object]) -> None:
    draft_chapters = draft.summary_data.get("chapters")
    enriched_chapters = summary_data.get("chapters")
    if not isinstance(draft_chapters, list) or not isinstance(enriched_chapters, list):
        raise ValueError("多模态总结缺少章节数据。")
    if len(draft_chapters) != len(enriched_chapters):
        raise ValueError("多模态总结不能新增、删除或重排章节。")
    for draft_chapter, enriched_chapter in zip(draft_chapters, enriched_chapters, strict=True):
        if not isinstance(draft_chapter, dict) or not isinstance(enriched_chapter, dict):
            raise ValueError("多模态总结章节格式无效。")
        for field in ("id", "start_seconds", "end_seconds"):
            if enriched_chapter.get(field) != draft_chapter.get(field):
                raise ValueError(f"多模态总结不能修改章节 {field}。")


def _restore_frame_references(*, summary_data: dict[str, object], frames: list[ExtractedChapterFrame]) -> None:
    by_chapter = {frame.chapter_id: frame for frame in frames}
    chapters = summary_data.get("chapters")
    if not isinstance(chapters, list):
        return
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        chapter.pop("image_timestamp_seconds", None)
        chapter.pop("image_filename", None)
        frame = by_chapter.get(str(chapter.get("id", "")))
        if frame is not None:
            chapter["image_timestamp_seconds"] = frame.timestamp_seconds
            chapter["image_filename"] = frame.image_filename


def _validate_visual_evidence(
    evidence: VisualEvidencePayload,
    frames: list[ExtractedChapterFrame],
) -> VisualEvidencePayload:
    allowed = {frame.image_filename: frame for frame in frames}
    result = []
    seen: set[str] = set()
    for item in evidence.frames:
        frame = allowed.get(item.image_filename)
        if frame is None:
            raise ValueError("视觉证据引用了未抽取的图片。")
        if item.image_filename in seen:
            raise ValueError("同一图片只能有一条视觉证据。")
        if item.chapter_id != frame.chapter_id or item.timestamp_seconds != frame.timestamp_seconds:
            raise ValueError("视觉证据的章节或时间点与实际截图不一致。")
        text = item.text.strip()
        if not text:
            raise ValueError("视觉证据文本不能为空。")
        seen.add(item.image_filename)
        result.append(item.model_copy(update={"text": text}))
    return VisualEvidencePayload(frames=result)
