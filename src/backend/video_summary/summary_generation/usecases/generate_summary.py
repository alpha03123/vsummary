from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
import shutil
from uuid import uuid4

from backend.video_summary.summary_generation.models import SummaryDocument, VideoAsset
from backend.video_summary.summary_generation.cancellation import GenerationCancellationContext
from backend.video_summary.summary_generation.ports import (
    GenerationArtifactStore,
    MediaProcessor,
    ProgressReporter,
    Summarizer,
    TranscriptEnhancer,
    Transcriber,
)
from backend.video_summary.summary_generation.stage_cache import GenerationStageCache


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
        staging_dir = output_dir.parent / f".{output_dir.name}.generation-{uuid4().hex}.tmp"
        await asyncio.to_thread(staging_dir.mkdir, parents=True, exist_ok=False)
        try:
            return await self._run_to_staging(
                video_path=video_path,
                output_dir=output_dir,
                staging_dir=staging_dir,
                progress_reporter=progress_reporter,
                cancellation=cancellation,
            )
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
    ) -> SummaryDocument:
        audio_path = staging_dir / "audio.wav"
        transcript_stem = staging_dir / "transcript"
        stage_cache = GenerationStageCache(output_dir / ".cache", video_path)
        media_identity = _cache_identity(self._media_processor)
        transcriber_identity = _cache_identity(self._transcriber)
        enhancer_identity = (
            _cache_identity(self._transcript_enhancer)
            if self._transcript_enhancer is not None
            else ""
        )

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
        audio_restored = await asyncio.to_thread(stage_cache.restore_audio, audio_path, identity=media_identity)
        if not audio_restored:
            await asyncio.to_thread(self._media_processor.extract_audio, video_path, audio_path, cancellation)
            _raise_if_cancelled(progress_reporter)
            await asyncio.to_thread(stage_cache.store_audio, audio_path, identity=media_identity)
        _raise_if_cancelled(progress_reporter)

        if progress_reporter is not None:
            progress_reporter.update("transcribe", 20.0, "正在使用 Whisper 转写音频")
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
            _raise_if_cancelled(progress_reporter)
            await asyncio.to_thread(
                stage_cache.store_transcript,
                "whisper",
                transcript,
                identity=transcriber_identity,
            )
        _raise_if_cancelled(progress_reporter)

        if self._transcript_enhancer is not None:
            if progress_reporter is not None:
                progress_reporter.update("enhance_transcript", 78.0, "正在用 AI 修正转写文本")
            _raise_if_cancelled(progress_reporter)
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
                _raise_if_cancelled(progress_reporter)
                await asyncio.to_thread(
                    stage_cache.store_transcript,
                    "transcript-enhance",
                    enhanced_transcript,
                    identity=enhancer_identity,
                )
            transcript = enhanced_transcript
            _raise_if_cancelled(progress_reporter)
            await self._artifact_store.save_enhanced_transcript(
                transcript=transcript,
                output_dir=staging_dir,
            )
            _raise_if_cancelled(progress_reporter)

        await self._artifact_store.save_cleaned_transcript(
            video=video,
            transcript=transcript,
            output_dir=staging_dir,
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
        await self._artifact_store.save_summary_document(document=summary_document, output_dir=staging_dir)
        _raise_if_cancelled(progress_reporter)
        await asyncio.to_thread(_commit_generation_artifacts, staging_dir, output_dir)
        return summary_document


def _build_llm_stage_error(stage_label: str, error: Exception) -> str:
    if _contains_connection_failure(error):
        return f"{stage_label}失败：无法连接到模型网关，请检查模型服务是否已启动，以及 provider settings 中的 Base URL 是否可用。"
    return f"{stage_label}失败：{error}"


def _cache_identity(component: object) -> str:
    explicit_identity = getattr(component, "cache_identity", None)
    if isinstance(explicit_identity, str) and explicit_identity.strip():
        return explicit_identity.strip()
    component_type = type(component)
    return f"{component_type.__module__}.{component_type.__qualname__}"


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


def _commit_generation_artifacts(staging_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in staging_dir.iterdir():
        target = output_dir / source.name
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(source), str(target))
            continue
        source.replace(target)


def _remove_tree_if_exists(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
