from __future__ import annotations

import asyncio
from pathlib import Path

from backend.video_summary.domain.models import SummaryDocument, VideoAsset
from backend.video_summary.generation.ports import (
    GenerationArtifactStore,
    MediaProcessor,
    ProgressReporter,
    Summarizer,
    TranscriptEnhancer,
    Transcriber,
)


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
    ) -> SummaryDocument:
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

        if progress_reporter is not None:
            progress_reporter.update("extract_audio", 15.0, "正在将视频转换为音频")
        await asyncio.to_thread(self._media_processor.extract_audio, video_path, audio_path)
        if progress_reporter is not None:
            progress_reporter.update("transcribe", 20.0, "正在使用 Whisper 转写音频")
        transcript = await asyncio.to_thread(
            self._transcriber.transcribe,
            audio_path,
            transcript_stem,
            None
            if progress_reporter is None
            else lambda ratio: progress_reporter.update(
                "transcribe",
                20.0 + max(0.0, min(1.0, ratio)) * 55.0,
                "Whisper 正在转写音频",
            ),
        )

        if self._transcript_enhancer is not None:
            if progress_reporter is not None:
                progress_reporter.update("enhance_transcript", 78.0, "正在用 AI 修正转写文本")
            try:
                transcript = await self._transcript_enhancer.enhance(video, transcript)
            except Exception as error:
                raise RuntimeError(_build_llm_stage_error("AI 内容增强", error)) from error
            await self._artifact_store.save_enhanced_transcript(
                transcript=transcript,
                output_dir=output_dir,
            )

        await self._artifact_store.save_cleaned_transcript(
            video=video,
            transcript=transcript,
            output_dir=output_dir,
        )

        if progress_reporter is not None:
            progress_reporter.update("summarize", 88.0, "正在生成 AI 概况")
        try:
            summary_document = await self._summarizer.summarize(video, transcript)
        except Exception as error:
            raise RuntimeError(_build_llm_stage_error("AI 概况生成", error)) from error
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
