from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

from backend.video_summary.domain.models import SummaryDocument, VideoAsset
from backend.video_summary.generation.cancellation import GenerationCancellationContext
from backend.video_summary.generation.ports import (
    GenerationArtifactStore,
    MediaProcessor,
    ProgressReporter,
    Summarizer,
    TranscriptEnhancer,
    Transcriber,
)


class GenerateCancelledError(RuntimeError):
    pass


class GenerateVideoSummary:
    def __init__(
        self,
        media_processor: MediaProcessor,
        transcriber: Transcriber,
        transcript_enhancer: TranscriptEnhancer | None,
        summarizer: Summarizer,
        artifact_store: GenerationArtifactStore,
    ) -> None:
        self._media_processor = media_processor
        self._transcriber = transcriber
        self._transcript_enhancer = transcript_enhancer
        self._summarizer = summarizer
        self._artifact_store = artifact_store

    async def run(
        self,
        video_path: Path,
        output_dir: Path,
        progress_reporter: ProgressReporter | None = None,
        cancellation: GenerationCancellationContext | None = None,
    ) -> SummaryDocument:
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
    ) -> SummaryDocument:
        _raise_if_cancelled(progress_reporter)
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
        audio_path = output_dir / "audio.wav"
        transcript_stem = output_dir / "transcript"

        if progress_reporter is not None:
            progress_reporter.update("probe", 5.0, "正在分析视频信息")
        video = VideoAsset(
            source_path=video_path,
            title=video_path.stem,
            duration_seconds=await asyncio.to_thread(self._media_processor.probe_duration, video_path),
        )
        _raise_if_cancelled(progress_reporter)

        if progress_reporter is not None:
            progress_reporter.update("extract_audio", 15.0, "正在将视频转换为音频")
        await asyncio.to_thread(self._media_processor.extract_audio, video_path, audio_path, cancellation)
        _raise_if_cancelled(progress_reporter)

        if progress_reporter is not None:
            progress_reporter.update("transcribe", 20.0, "正在使用 Whisper 转写音频")
        transcript = await asyncio.to_thread(
            self._transcriber.transcribe,
            audio_path,
            transcript_stem,
            None
            if progress_reporter is None
            else lambda ratio: _handle_transcribe_progress(progress_reporter, ratio),
        )
        _raise_if_cancelled(progress_reporter)

        if self._transcript_enhancer is not None:
            if progress_reporter is not None:
                progress_reporter.update("enhance_transcript", 78.0, "正在用 AI 修正转写文本")
            _raise_if_cancelled(progress_reporter)
            try:
                transcript = await self._transcript_enhancer.enhance(video, transcript, cancellation)
            except GenerateCancelledError:
                raise
            except Exception as error:
                raise RuntimeError(_build_llm_stage_error("AI 内容增强", error)) from error
            _raise_if_cancelled(progress_reporter)
            await self._artifact_store.save_enhanced_transcript(
                transcript=transcript,
                output_dir=output_dir,
            )
            _raise_if_cancelled(progress_reporter)

        await self._artifact_store.save_cleaned_transcript(
            video=video,
            transcript=transcript,
            output_dir=output_dir,
        )
        _raise_if_cancelled(progress_reporter)

        if progress_reporter is not None:
            progress_reporter.update("summarize", 88.0, "正在生成 AI 概况")
        _raise_if_cancelled(progress_reporter)
        try:
            summary_document = await self._summarizer.summarize(video, transcript, cancellation)
        except GenerateCancelledError:
            raise
        except Exception as error:
            raise RuntimeError(_build_llm_stage_error("AI 概况生成", error)) from error
        _raise_if_cancelled(progress_reporter)
        await self._artifact_store.save_summary_document(document=summary_document, output_dir=output_dir)
        return summary_document


def _build_llm_stage_error(stage_label: str, error: Exception) -> str:
    if _contains_connection_failure(error):
        return f"{stage_label}失败：无法连接到模型网关，请检查模型服务是否已启动，以及 provider settings 中的 Base URL 是否可用。"
    return f"{stage_label}失败：{error}"


def _contains_connection_failure(error: BaseException) -> bool:
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
    _raise_if_cancelled(progress_reporter)
    progress_reporter.update(
        "transcribe",
        20.0 + max(0.0, min(1.0, ratio)) * 55.0,
        "Whisper 正在转写音频",
    )


async def _mirror_progress_cancellation(
    progress_reporter: ProgressReporter,
    cancellation: GenerationCancellationContext,
) -> None:
    while not cancellation.cancel_requested:
        if progress_reporter.is_cancel_requested():
            cancellation.request_cancel()
            return
        await asyncio.sleep(0.05)


def _raise_if_cancelled(progress_reporter: ProgressReporter | None) -> None:
    if progress_reporter is None:
        return
    try:
        progress_reporter.raise_if_cancelled()
    except RuntimeError as error:
        raise GenerateCancelledError(str(error) or "生成已取消") from error
