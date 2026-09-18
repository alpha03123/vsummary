"""单视频总结生成用例（生成层编排核心）。

按 `探测 → 抽音频 → 转写 → （可选）增强 → 落转写 → LLM 总结 → 提交`
的流水线把视频转换为结构化总结文档。中间产物全部在 staging 目录
下生成，最终通过原子 move 提交到 `output_dir`，保证失败时不会
污染既有制品。

进度上报：
- 阶段名（`stage`）：`probe` / `extract_audio` / `transcribe` /
  `enhance_transcript` / `summarize`；
- 转写阶段会按 0.0-1.0 的 ratio 把进度插值到 20%-75% 区间；
- 失败/取消会被翻译为 SSE 事件，由 `ProgressReporter` 实现方路由。

错误处理与重试：
- 不做自动重试；调用方如需重试应重新触发整个用例；
- LLM 阶段的异常会被包装为带中文错误信息的 `RuntimeError`，
  若底层是连接错误，会附带「请检查 Base URL」提示；
- 取消信号来自 `ProgressReporter.is_cancel_requested` 或外部
  传入的 `GenerationCancellationContext`，触发后会中断正在进行
  的 LLM 调用与子进程，staging 目录会被清理。
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import math
from pathlib import Path
import shutil
from uuid import uuid4

from backend.video_summary.domain.models import ManualTranscriptInput, SummaryDocument, Transcript, TranscriptSegment, VideoAsset
from backend.video_summary.generation.cancellation import GenerationCancellationContext
from backend.video_summary.generation.renderers import render_markdown
from backend.video_summary.generation.ports import (
    FrameExtractor,
    GenerationArtifactStore,
    MediaProcessor,
    ManualTranscriptSource,
    NoTranscribableAudioError,
    NoVideoFramesError,
    ProgressReporter,
    SavedTranscriptSource,
    SubtitleTranscriptSource,
    Summarizer,
    TranscriptEnhancer,
    Transcriber,
    VisualSummaryEnricher,
)
from backend.video_summary.generation.stage_cache import GenerationStageCache
from backend.video_summary.generation.visuals import ExtractedChapterFrame, PlannedChapterFrame


LOGGER = logging.getLogger(__name__)

PROCESSING_MODES = {"summary", "transcript"}


class GenerateCancelledError(RuntimeError):
    """生成任务被用户取消时抛出的业务异常。"""


class GenerateVideoSummary:
    """单视频总结生成用例（生成层核心编排）。

    编排流水线（任一阶段被取消都会立刻中断后续步骤）：
    1. `probe_duration` 获取视频时长；
    2. `extract_audio` 从视频抽取音频（按媒体实现身份做缓存复用）；
    3. `transcribe` 转写音频为 `Transcript`（按转写实现身份做缓存复用）；
    4. 可选 `enhance` 用 LLM 修正 ASR 噪声（按增强实现身份做缓存复用）；
    5. 落盘「增强后转写」「清洗后转写」；
    6. `summarize` 调用 LLM 生成 `SummaryDocument`；
    7. 落盘总结文档，并把 staging 目录原子提交到 `output_dir`。

    持久化 vs 临时：
    - 持久化：`output_dir` 下的制品（仅在第 7 步原子提交后可见）；
    - 临时：`staging_dir` 下的中间文件（任一阶段失败/取消都会被清理）；
    - 缓存：`output_dir/.cache`（按 manifest 复用，下一次同视频可跳过）。
    """

    def __init__(
        self,
        media_processor: MediaProcessor,
        transcriber: Transcriber,
        transcript_enhancer: TranscriptEnhancer | None,
        summarizer: Summarizer,
        artifact_store: GenerationArtifactStore,
        subtitle_provider: SubtitleTranscriptSource | None = None,
        manual_transcript_provider: ManualTranscriptSource | None = None,
        saved_transcript_provider: SavedTranscriptSource | None = None,
        frame_extractor: FrameExtractor | None = None,
        chapter_screenshots_enabled: bool = True,
        visual_summary_enricher: VisualSummaryEnricher | None = None,
        multimodal_visual_enabled: bool = False,
        max_visual_frames: int = 6,
    ) -> None:
        """注入媒体处理、转写、（可选）转写增强、总结与制品落盘端口。

        Args:
            media_processor: 用于探测时长与抽取音频的端口。
            transcriber: 同步转写端口（实现内自行管理线程）。
            transcript_enhancer: 可选的转写增强端口；为 `None` 时跳过
                「AI 修正」阶段。
            summarizer: LLM 总结端口。
            artifact_store: 制品落盘端口。
        """
        self._media_processor = media_processor
        self._transcriber = transcriber
        self._transcript_enhancer = transcript_enhancer
        self._summarizer = summarizer
        self._artifact_store = artifact_store
        self._subtitle_provider = subtitle_provider
        self._manual_transcript_provider = manual_transcript_provider
        self._saved_transcript_provider = saved_transcript_provider
        self._frame_extractor = frame_extractor
        self._chapter_screenshots_enabled = chapter_screenshots_enabled
        self._visual_summary_enricher = visual_summary_enricher
        self._multimodal_visual_enabled = multimodal_visual_enabled
        self._max_visual_frames = max_visual_frames
        if self._multimodal_visual_enabled and not self._chapter_screenshots_enabled:
            raise ValueError("启用多模态视觉增强前必须先启用章节截图。")
        if self._max_visual_frames <= 0:
            raise ValueError("max_visual_frames 必须是正整数。")

    async def run(
        self,
        video_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        cancellation: GenerationCancellationContext | None = None,
        manual_transcript: ManualTranscriptInput | None = None,
        use_saved_manual_transcript: bool = True,
        processing_mode: str = "summary",
    ) -> SummaryDocument | None:
        """为指定视频生成结构化总结文档。

        Args:
            video_path: 视频源文件路径。
            output_dir: 制品最终写入目录。
            progress_reporter: 可选进度上报端口；为 `None` 时不进行 SSE 上报。
            cancellation: 可选的外部取消上下文；为 `None` 且提供了
                `progress_reporter` 时会自动创建一个，并把 reporter 的
                `is_cancel_requested` 镜像到内部 `GenerationCancellationContext`。

        Returns:
            最终生成的结构化 `SummaryDocument`。

        Raises:
            GenerateCancelledError: 用户取消生成时抛出。
            RuntimeError: LLM 阶段异常会被包装为带中文提示的 `RuntimeError`。
            LookupError: 底层端口抛出的「无制品」错误。
        """
        if processing_mode not in PROCESSING_MODES:
            raise ValueError(f"unsupported processing mode: {processing_mode}")
        resolved_cancellation = cancellation
        cancel_watch_task: asyncio.Task[None] | None = None
        if resolved_cancellation is None and progress_reporter is not None:
            resolved_cancellation = GenerationCancellationContext(str(output_dir))
            cancel_watch_task = asyncio.create_task(
                _mirror_progress_cancellation(progress_reporter, resolved_cancellation)
            )

        try:
            return await self._run_with_cancellation(
                video_path=video_path,
                output_dir=output_dir,
                progress_reporter=progress_reporter,
                cancellation=resolved_cancellation,
                manual_transcript=manual_transcript,
                use_saved_manual_transcript=use_saved_manual_transcript,
                processing_mode=processing_mode,
            )
        finally:
            if cancel_watch_task is not None:
                cancel_watch_task.cancel()
                with suppress(asyncio.CancelledError):
                    await cancel_watch_task

    async def _run_with_cancellation(
        self,
        *,
        video_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None,
        cancellation: GenerationCancellationContext | None,
        manual_transcript: ManualTranscriptInput | None,
        use_saved_manual_transcript: bool,
        processing_mode: str,
    ) -> SummaryDocument | None:
        """前置取消检查 → 准备 staging 目录 → 跑核心流水线 → 清理 staging。

        任何阶段失败/取消都会通过 `finally` 清理 staging 目录，
        确保既有 `output_dir` 不会被污染。若 staging 目录在流水线中被
        异常删除，则只重试一次，并复用已完成的阶段缓存。
        """
        _raise_if_cancelled(progress_reporter, cancellation)
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
        for attempt in range(2):
            staging_dir = output_dir.parent / f".{output_dir.name}.generation-{uuid4().hex}.tmp"
            await asyncio.to_thread(staging_dir.mkdir, parents=True, exist_ok=False)
            try:
                return await self._run_to_staging(
                    video_path=video_path,
                    output_dir=output_dir,
                    staging_dir=staging_dir,
                    progress_reporter=progress_reporter,
                    cancellation=cancellation,
                    manual_transcript=manual_transcript,
                    use_saved_manual_transcript=use_saved_manual_transcript,
                    processing_mode=processing_mode,
                )
            except FileNotFoundError:
                if attempt == 0 and not staging_dir.exists():
                    continue
                raise
            finally:
                await asyncio.to_thread(_remove_tree_if_exists, staging_dir)

    async def _run_to_staging(
        self,
        *,
        video_path: Path,
        output_dir: Path,
        staging_dir: Path,
        progress_reporter: ProgressReporter | None,
        cancellation: GenerationCancellationContext | None,
        manual_transcript: ManualTranscriptInput | None,
        use_saved_manual_transcript: bool,
        processing_mode: str,
    ) -> SummaryDocument | None:
        """在 staging 目录下依次跑各生成阶段，全部成功后原子提交到 `output_dir`。

        每个阶段都会：
        1. 视情况推进 `progress_reporter`；
        2. 优先尝试从 `GenerationStageCache` 复用上一次的中间产物；
        3. 在阻塞调用之前检查取消信号，避免浪费昂贵的计算。
        """
        stage_cache = GenerationStageCache(output_dir / ".cache", video_path)
        unavailable_reason: str | None = None
        resolved_manual_transcript = manual_transcript
        if resolved_manual_transcript is None and use_saved_manual_transcript and self._manual_transcript_provider is not None:
            resolved_manual_transcript = await asyncio.to_thread(
                self._manual_transcript_provider.load,
                output_dir,
            )

        saved_transcript = None
        if (
            processing_mode == "summary"
            and resolved_manual_transcript is None
            and use_saved_manual_transcript
            and self._saved_transcript_provider is not None
        ):
            saved_transcript = await asyncio.to_thread(self._saved_transcript_provider.load, output_dir)

        subtitle_transcript = None
        if resolved_manual_transcript is not None:
            transcript = resolved_manual_transcript.transcript
            video = VideoAsset(
                source_path=video_path,
                title=video_path.stem,
                duration_seconds=max(segment.end_seconds for segment in transcript.segments),
            )
            transcript_source_identity = "manual-srt-v1"
            if progress_reporter is not None:
                progress_reporter.update("load_manual_srt", 20.0, "已读取人工 SRT，跳过字幕探测和语音识别")
        elif saved_transcript is not None:
            transcript = saved_transcript
            video = VideoAsset(
                source_path=video_path,
                title=video_path.stem,
                duration_seconds=max(segment.end_seconds for segment in transcript.segments),
            )
            transcript_source_identity = "saved-transcript-v1"
            if progress_reporter is not None:
                progress_reporter.update("load_transcript", 80.0, "已读取现有字幕，跳过字幕获取和语音识别")
        elif self._subtitle_provider is not None:
            if progress_reporter is not None:
                progress_reporter.update("probe_subtitles", 5.0, "正在检查中文字幕")
            try:
                subtitle_transcript = await asyncio.to_thread(
                    self._subtitle_provider.load,
                    video_path,
                    staging_dir,
                    cancellation,
                )
            except InterruptedError as error:
                raise GenerateCancelledError(str(error) or "生成已取消") from error
            _raise_if_cancelled(progress_reporter, cancellation)

        if resolved_manual_transcript is None and saved_transcript is None and subtitle_transcript is not None:
            video = VideoAsset(
                source_path=video_path,
                title=video_path.stem,
                duration_seconds=max(segment.end_seconds for segment in subtitle_transcript.segments),
            )
            transcript = subtitle_transcript
            transcript_source_identity = f"subtitle:{_cache_identity(self._subtitle_provider)}"
            if progress_reporter is not None:
                progress_reporter.update("extract_subtitles", 20.0, "已读取中文字幕，跳过语音识别")
        elif resolved_manual_transcript is None and saved_transcript is None:
            audio_path = staging_dir / "audio.wav"
            transcript_stem = staging_dir / "transcript"
            media_identity = _cache_identity(self._media_processor)
            transcriber_identity = _cache_identity(self._transcriber)
            transcript_source_identity = f"whisper:{transcriber_identity}"
            if progress_reporter is not None:
                progress_reporter.update("probe", 5.0, "未找到可用中文字幕，正在分析视频信息")
            video = VideoAsset(
                source_path=video_path,
                title=video_path.stem,
                duration_seconds=await asyncio.to_thread(self._media_processor.probe_duration, video_path),
            )
            _raise_if_cancelled(progress_reporter, cancellation)

            if progress_reporter is not None:
                progress_reporter.update("extract_audio", 15.0, "正在将视频转换为音频")
            try:
                audio_restored = await asyncio.to_thread(stage_cache.restore_audio, audio_path, identity=media_identity)
                if not audio_restored:
                    await asyncio.to_thread(self._media_processor.extract_audio, video_path, audio_path, cancellation)
                    _raise_if_cancelled(progress_reporter, cancellation)
                    await asyncio.to_thread(stage_cache.store_audio, audio_path, identity=media_identity)
            except NoTranscribableAudioError:
                unavailable_reason = "未找到可用中文字幕，且视频不含可供转写的音频流。"
                transcript_source_identity = "no-transcribable-audio-v1"
                transcript = await asyncio.to_thread(
                    stage_cache.load_transcript,
                    "no-transcribable-audio",
                    identity=transcript_source_identity,
                )
                if transcript is None:
                    transcript = _build_no_transcribable_audio_transcript(video.duration_seconds)
                    await asyncio.to_thread(
                        stage_cache.store_transcript,
                        "no-transcribable-audio",
                        transcript,
                        identity=transcript_source_identity,
                    )
                if progress_reporter is not None:
                    progress_reporter.update("transcribe", 80.0, "视频没有可供转写的信息，正在写入占位概况")
            else:
                _raise_if_cancelled(progress_reporter, cancellation)

                if progress_reporter is not None:
                    progress_reporter.update("transcribe", 20.0, "正在转写音频")
                transcript = await asyncio.to_thread(stage_cache.load_transcript, "whisper", identity=transcriber_identity)
                if transcript is None:
                    transcript = await asyncio.to_thread(
                        self._transcriber.transcribe,
                        audio_path,
                        transcript_stem,
                        None
                        if progress_reporter is None
                        else lambda ratio: _handle_transcribe_progress(progress_reporter, ratio),
                    )
                    _raise_if_cancelled(progress_reporter, cancellation)
                    await asyncio.to_thread(
                        stage_cache.store_transcript,
                        "whisper",
                        transcript,
                        identity=transcriber_identity,
                    )
            _raise_if_cancelled(progress_reporter, cancellation)

        enhancer_identity = (
            f"{_cache_identity(self._transcript_enhancer)}|source={transcript_source_identity}"
            if self._transcript_enhancer is not None
            else ""
        )
        if (
            self._transcript_enhancer is not None
            and unavailable_reason is None
            and resolved_manual_transcript is None
            and saved_transcript is None
        ):
            if progress_reporter is not None:
                progress_reporter.update("enhance_transcript", 78.0, "正在用 AI 修正转写文本")
            _raise_if_cancelled(progress_reporter, cancellation)
            enhanced_transcript = await asyncio.to_thread(
                stage_cache.load_transcript,
                "transcript-enhance",
                identity=enhancer_identity,
            )
            if enhanced_transcript is None:
                try:
                    enhanced_transcript = await self._transcript_enhancer.enhance(video, transcript, cancellation)
                except GenerateCancelledError:
                    raise
                except Exception as error:
                    raise RuntimeError(_build_llm_stage_error("AI 内容增强", error)) from error
                _raise_if_cancelled(progress_reporter, cancellation)
                await asyncio.to_thread(
                    stage_cache.store_transcript,
                    "transcript-enhance",
                    enhanced_transcript,
                    identity=enhancer_identity,
                )
            transcript = enhanced_transcript
            _raise_if_cancelled(progress_reporter, cancellation)
            await self._artifact_store.save_enhanced_transcript(
                transcript=transcript,
                output_dir=staging_dir,
            )
            _raise_if_cancelled(progress_reporter, cancellation)

        if resolved_manual_transcript is not None:
            await self._artifact_store.save_manual_transcript(
                manual_transcript=resolved_manual_transcript,
                output_dir=staging_dir,
            )
            _raise_if_cancelled(progress_reporter, cancellation)

        await self._artifact_store.save_cleaned_transcript(
            video=video,
            transcript=transcript,
            output_dir=staging_dir,
        )
        _raise_if_cancelled(progress_reporter, cancellation)

        if processing_mode == "transcript":
            if unavailable_reason is not None:
                raise RuntimeError(unavailable_reason)
            await asyncio.to_thread(
                _commit_transcript_artifacts,
                staging_dir,
                output_dir,
                remove_manual_source=not use_saved_manual_transcript,
            )
            return None

        if unavailable_reason is not None:
            summary_document = _build_no_transcribable_audio_summary(video, unavailable_reason)
        else:
            if progress_reporter is not None:
                progress_reporter.update("summarize", 88.0, "正在生成 AI 概况")
            _raise_if_cancelled(progress_reporter, cancellation)
            try:
                summary_document = await self._summarizer.summarize(video, transcript, cancellation)
            except GenerateCancelledError:
                raise
            except Exception as error:
                raise RuntimeError(_build_llm_stage_error("AI 概况生成", error)) from error
        _raise_if_cancelled(progress_reporter, cancellation)
        extracted_frames: list[ExtractedChapterFrame] = []
        if self._chapter_screenshots_enabled:
            summary_document, extracted_frames = await _attach_chapter_screenshots(
                summary_document,
                video=video,
                staging_dir=staging_dir,
                frame_extractor=self._frame_extractor,
                progress_reporter=progress_reporter,
                cancellation=cancellation,
                max_visual_frames=self._max_visual_frames,
            )
        visual_frames = _select_visual_analysis_frames(extracted_frames, self._max_visual_frames)
        if self._multimodal_visual_enabled and visual_frames:
            if self._visual_summary_enricher is None:
                raise RuntimeError("多模态视觉增强未配置模型适配器。")
            if progress_reporter is not None:
                progress_reporter.update("enrich_visual_summary", 98.0, "正在结合截图生成最终概况")
            _raise_if_cancelled(progress_reporter, cancellation)
            try:
                summary_document, visual_evidence = await self._visual_summary_enricher.enrich(
                    video=video,
                    transcript=transcript,
                    draft=summary_document,
                    frames=visual_frames,
                    cancellation=cancellation,
                )
                summary_document = _restore_display_frame_references(summary_document, extracted_frames)
            except GenerateCancelledError:
                raise
            except Exception:
                LOGGER.exception("多模态视觉增强失败，保留文本概况和章节截图")
                if progress_reporter is not None:
                    progress_reporter.update("enrich_visual_summary", 99.0, "文本概况已完成；本次未能解析画面")
            else:
                _raise_if_cancelled(progress_reporter, cancellation)
                await self._artifact_store.save_visual_evidence(evidence=visual_evidence, output_dir=staging_dir)
        await self._artifact_store.save_summary_document(document=summary_document, output_dir=staging_dir)
        _raise_if_cancelled(progress_reporter, cancellation)
        await asyncio.to_thread(
            _commit_generation_artifacts,
            staging_dir,
            output_dir,
            remove_manual_source=not use_saved_manual_transcript,
        )
        return summary_document


async def _attach_chapter_screenshots(
    document: SummaryDocument,
    *,
    video: VideoAsset,
    staging_dir: Path,
    frame_extractor: FrameExtractor | None,
    progress_reporter: ProgressReporter | None,
    cancellation: GenerationCancellationContext | None,
    max_visual_frames: int,
) -> tuple[SummaryDocument, list[ExtractedChapterFrame]]:
    """按模型规划时间点抽取章节截图；音频媒体不产生视觉制品。"""
    chapters = document.summary_data.get("chapters")
    if frame_extractor is None or not isinstance(chapters, list) or not chapters:
        return document, []

    summary_data = dict(document.summary_data)
    plans = validate_visual_frame_plan(document=document, video=video, max_visual_frames=max_visual_frames)
    plan_by_chapter_id = {plan.chapter_id: plan for plan in plans}
    enriched_chapters: list[object] = []
    extracted_frames: list[ExtractedChapterFrame] = []
    screenshot_dir = staging_dir / "screenshots"
    for index, raw_chapter in enumerate(chapters, start=1):
        if not isinstance(raw_chapter, dict):
            enriched_chapters.append(raw_chapter)
            continue
        plan = plan_by_chapter_id.get(str(raw_chapter.get("id", "")).strip())
        if plan is None:
            enriched_chapters.append(raw_chapter)
            continue
        if progress_reporter is not None:
            progress_reporter.update(
                "extract_screenshots",
                92.0 + len(extracted_frames) * 6.0 / max(1, len(plans)),
                f"正在生成章节插图 {len(extracted_frames) + 1}/{len(plans)}",
            )
        _raise_if_cancelled(progress_reporter, cancellation)
        try:
            await asyncio.to_thread(
                frame_extractor.extract_frame,
                video.source_path,
                plan.timestamp_seconds,
                screenshot_dir / plan.image_filename,
                cancellation,
            )
        except InterruptedError as error:
            raise GenerateCancelledError(str(error) or "生成已取消") from error
        except NoVideoFramesError:
            LOGGER.info(
                "媒体不含视频流，跳过章节截图",
                extra={"event": "chapter_screenshot_skipped_no_video_stream"},
            )
            enriched_chapters.append(raw_chapter)
            enriched_chapters.extend(chapters[index:])
            summary_data["chapters"] = enriched_chapters
            return SummaryDocument(
                markdown=render_markdown(summary_data),
                summary_data=summary_data,
                mindmap_data=document.mindmap_data,
            ), []
        except Exception:
            LOGGER.exception("章节截图生成失败", extra={"chapter_id": plan.chapter_id})
            enriched_chapters.append(raw_chapter)
            continue
        _raise_if_cancelled(progress_reporter, cancellation)
        enriched_chapters.append({**raw_chapter, "image_filename": plan.image_filename})
        extracted_frames.append(
            ExtractedChapterFrame(
                chapter_id=plan.chapter_id,
                timestamp_seconds=plan.timestamp_seconds,
                image_filename=plan.image_filename,
                path=screenshot_dir / plan.image_filename,
            )
        )

    summary_data["chapters"] = enriched_chapters
    return SummaryDocument(
        markdown=render_markdown(summary_data),
        summary_data=summary_data,
        mindmap_data=document.mindmap_data,
    ), extracted_frames


def validate_visual_frame_plan(
    *,
    document: SummaryDocument,
    video: VideoAsset,
    max_visual_frames: int,
) -> list[PlannedChapterFrame]:
    """验证每章一张的截图计划；读图配额不在此处裁剪。"""
    if max_visual_frames <= 0:
        raise ValueError("max_visual_frames 必须是正整数。")
    chapters = document.summary_data.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("总结章节数据无效。")
    plans: list[PlannedChapterFrame] = []
    seen_ids: set[str] = set()
    for index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            raise ValueError(f"第 {index} 章数据不是对象。")
        chapter_id = str(chapter.get("id", "")).strip()
        if not chapter_id or chapter_id in seen_ids:
            raise ValueError(f"第 {index} 章 ID 无效或重复。")
        seen_ids.add(chapter_id)
        timestamp = chapter.get("image_timestamp_seconds")
        if timestamp is None:
            raise ValueError(f"第 {index} 章缺少章节截图时间点。")
        start = chapter.get("start_seconds")
        end = chapter.get("end_seconds")
        if not all(isinstance(value, int | float) and math.isfinite(value) for value in (timestamp, start, end)):
            raise ValueError(f"第 {index} 章截图时间范围无效。")
        if end < start or timestamp < start or timestamp > end or timestamp < 0 or timestamp > video.duration_seconds:
            raise ValueError(f"第 {index} 章截图时间点不在有效范围内。")
        plans.append(
            PlannedChapterFrame(
                chapter_id=chapter_id,
                timestamp_seconds=float(timestamp),
                image_filename=f"chapter-{index:02d}.jpg",
            )
        )
    if len(plans) != len(chapters):
        raise ValueError("每个章节都必须提供一个截图时间点。")
    return plans


def _select_visual_analysis_frames(
    frames: list[ExtractedChapterFrame],
    max_visual_frames: int,
) -> list[ExtractedChapterFrame]:
    """从每章展示帧中确定性选出受视觉 token 配额限制的读图子集。"""
    if len(frames) <= max_visual_frames:
        return frames
    if max_visual_frames <= 0:
        raise ValueError("max_visual_frames 必须是正整数。")
    if max_visual_frames == 1:
        return [frames[0]]
    last_index = len(frames) - 1
    indexes = {
        round(position * last_index / (max_visual_frames - 1))
        for position in range(max_visual_frames)
    }
    return [frame for index, frame in enumerate(frames) if index in indexes]


def _restore_display_frame_references(
    document: SummaryDocument,
    frames: list[ExtractedChapterFrame],
) -> SummaryDocument:
    """视觉增强只读取子集时，仍由系统恢复所有章节的展示帧绑定。"""
    frames_by_chapter = {frame.chapter_id: frame for frame in frames}
    chapters = document.summary_data.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("多模态总结缺少章节数据。")
    summary_data = dict(document.summary_data)
    restored_chapters: list[object] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise ValueError("多模态总结章节格式无效。")
        restored = dict(chapter)
        restored.pop("image_timestamp_seconds", None)
        restored.pop("image_filename", None)
        frame = frames_by_chapter.get(str(chapter.get("id", "")))
        if frame is not None:
            restored["image_timestamp_seconds"] = frame.timestamp_seconds
            restored["image_filename"] = frame.image_filename
        restored_chapters.append(restored)
    summary_data["chapters"] = restored_chapters
    return SummaryDocument(
        markdown=render_markdown(summary_data),
        summary_data=summary_data,
        mindmap_data=document.mindmap_data,
    )


def _build_no_transcribable_audio_transcript(duration_seconds: float) -> Transcript:
    return Transcript(
        language="und",
        segments=[
            TranscriptSegment(
                start_seconds=0.0,
                end_seconds=max(0.0, duration_seconds),
                text="该视频没有可供转写的音频或中文字幕。",
            )
        ],
    )


def _build_no_transcribable_audio_summary(video: VideoAsset, reason: str) -> SummaryDocument:
    summary_data = {
        "title": video.title,
        "transcription_status": "untranscribable",
        "one_sentence_summary": "该视频没有可供转写的信息，无法生成内容概况。",
        "core_problem": "",
        "chapters": [],
        "key_takeaways": [reason],
    }
    return SummaryDocument(markdown=render_markdown(summary_data), summary_data=summary_data)


def _build_llm_stage_error(stage_label: str, error: Exception) -> str:
    """构造面向用户的中文 LLM 阶段错误信息。

    如果底层异常链路里含有连接失败迹象，会附加「请检查 Base URL」
    的提示；否则退化为 `f"{stage_label}失败：{error}"`。

    Args:
        stage_label: 阶段显示名（如「AI 概况生成」「AI 内容增强」）。
        error: 底层异常对象。

    Returns:
        中文错误信息字符串。
    """
    if _contains_connection_failure(error):
        return f"{stage_label}失败：无法连接到模型网关，请检查模型服务是否已启动，以及 provider settings 中的 Base URL 是否可用。"
    return f"{stage_label}失败：{error}"


def _cache_identity(component: object) -> str:
    """推导组件的「缓存身份」字符串，用于 stage_cache manifest。

    优先使用组件显式声明的 `cache_identity` 属性；否则退化为组件
    类型的 `module.qualname`，确保不同实现实例的身份稳定可比较。

    Args:
        component: 待推导的端口实现实例。

    Returns:
        缓存身份字符串；始终为非空。
    """
    explicit_identity = getattr(component, "cache_identity", None)
    if isinstance(explicit_identity, str) and explicit_identity.strip():
        return explicit_identity.strip()
    component_type = type(component)
    return f"{component_type.__module__}.{component_type.__qualname__}"


def _contains_connection_failure(error: BaseException) -> bool:
    """判断异常链路里是否包含连接失败的迹象。

    沿 `__cause__` / `__context__` 链遍历所有异常，对每个异常的
    `str(...)` 做小写匹配，命中任一连接失败关键字即返回 `True`。

    Args:
        error: 起始异常对象。

    Returns:
        若链路里存在连接失败迹象则为 `True`。
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).lower()
        if (
            "connection refused" in message
            or "connect call failed" in message
            or "cannot connect to host" in message
            or "connection error" in message
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _handle_transcribe_progress(progress_reporter: ProgressReporter, ratio: float) -> None:
    """把转写器的内部 0.0-1.0 进度比换算成对外的 20%-75% 区间。

    先做一次取消检查，再以 `20.0 + ratio * 55.0` 的线性映射推进进度。

    Args:
        progress_reporter: 进度上报端口。
        ratio: 转写器内部进度（0.0-1.0）；会被夹紧后参与换算。
    """
    _raise_if_cancelled(progress_reporter)
    progress_reporter.update(
        "transcribe",
        20.0 + max(0.0, min(1.0, ratio)) * 55.0,
        "正在转写音频",
    )


async def _mirror_progress_cancellation(
    progress_reporter: ProgressReporter,
    cancellation: GenerationCancellationContext,
) -> None:
    """把 `progress_reporter` 的取消信号镜像到 `cancellation` 上下文。

    每 50ms 轮询一次 reporter；一旦 reporter 报告取消，立即调用
    `cancellation.request_cancel()` 并退出协程。
    """
    while not cancellation.cancel_requested:
        if progress_reporter.is_cancel_requested():
            cancellation.request_cancel()
            return
        await asyncio.sleep(0.05)


def _raise_if_cancelled(
    progress_reporter: ProgressReporter | None,
    cancellation: GenerationCancellationContext | None = None,
) -> None:
    """若 reporter 已收到取消信号，则抛 `GenerateCancelledError`。

    Args:
        progress_reporter: 可选进度上报端口；为 `None` 时直接返回。

    Raises:
        GenerateCancelledError: reporter 处于取消态时抛出。
    """
    if cancellation is not None and cancellation.cancel_requested:
        raise GenerateCancelledError("生成已取消")
    if progress_reporter is None:
        return
    try:
        progress_reporter.raise_if_cancelled()
    except RuntimeError as error:
        raise GenerateCancelledError(str(error) or "生成已取消") from error


def _commit_generation_artifacts(
    staging_dir: Path,
    output_dir: Path,
    *,
    remove_manual_source: bool = False,
) -> None:
    """把 staging 目录里的全部产物原子提交到 `output_dir`。

    目录条目使用 `shutil.move` 整体替换（先 `rmtree` 旧目录），文件
    条目使用 `Path.replace` 原子改名。整个提交过程是同步执行的。

    Args:
        staging_dir: 临时 staging 目录（提交完成后调用方负责清理）。
        output_dir: 最终制品目录。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    staged_names = {source.name for source in staging_dir.iterdir()}
    for source in staging_dir.iterdir():
        target = output_dir / source.name
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(source), str(target))
            continue
        source.replace(target)
    for artifact_name in ("transcript.enhanced.json", "mindmap.json", "knowledge_cards.json", "visual.evidence.json"):
        if artifact_name not in staged_names:
            (output_dir / artifact_name).unlink(missing_ok=True)
    if "screenshots" not in staged_names:
        _remove_tree_if_exists(output_dir / "screenshots")
    (output_dir.parent / "mindmap.json").unlink(missing_ok=True)
    if remove_manual_source:
        (output_dir / "transcript.manual.srt").unlink(missing_ok=True)
        (output_dir / "transcript.source.json").unlink(missing_ok=True)


def _commit_transcript_artifacts(
    staging_dir: Path,
    output_dir: Path,
    *,
    remove_manual_source: bool = False,
) -> None:
    """提交转写制品，并移除所有依赖旧转写的派生制品。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_artifacts = (
        "transcript.cleaned.json",
        "transcript.enhanced.json",
        "transcript.manual.srt",
        "transcript.source.json",
    )
    for artifact_name in transcript_artifacts:
        source = staging_dir / artifact_name
        target = output_dir / artifact_name
        if source.is_file():
            source.replace(target)
        elif artifact_name == "transcript.enhanced.json":
            target.unlink(missing_ok=True)
    if remove_manual_source:
        (output_dir / "transcript.manual.srt").unlink(missing_ok=True)
        (output_dir / "transcript.source.json").unlink(missing_ok=True)
    for artifact_name in ("summary.json", "summary.md", "mindmap.json", "knowledge_cards.json", "visual.evidence.json"):
        (output_dir / artifact_name).unlink(missing_ok=True)
    _remove_tree_if_exists(output_dir / "screenshots")
    (output_dir.parent / "mindmap.json").unlink(missing_ok=True)


def _remove_tree_if_exists(path: Path) -> None:
    """目录存在时 `shutil.rmtree` 递归删除；不存在时静默忽略。"""
    if path.exists():
        shutil.rmtree(path)
