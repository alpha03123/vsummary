from __future__ import annotations

import asyncio

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import Summarizer
from backend.video_summary.infrastructure.structured_generation import (
    SummaryPayload,
    build_chunk_prompt,
    build_document_prompt,
    build_transcript_document_prompt,
    chunk_segments,
    render_markdown,
)


class LiteLLMCompletionSummarizer(Summarizer):
    def __init__(
        self,
        gateway: LiteLLMCompletionGateway,
        *,
        context_window_tokens: int,
        reserved_output_tokens: int,
        direct_summary_threshold_ratio: float,
        summary_chunk_concurrency: int = 1,
    ) -> None:
        self._gateway = gateway
        self._context_window_tokens = context_window_tokens
        self._reserved_output_tokens = reserved_output_tokens
        self._direct_summary_threshold_ratio = direct_summary_threshold_ratio
        self._summary_chunk_concurrency = max(1, summary_chunk_concurrency)

    async def summarize(self, video: VideoAsset, transcript: Transcript) -> SummaryDocument:
        if _should_use_direct_summary(
            video=video,
            transcript=transcript,
            context_window_tokens=self._context_window_tokens,
            reserved_output_tokens=self._reserved_output_tokens,
            direct_summary_threshold_ratio=self._direct_summary_threshold_ratio,
        ):
            payload = await self._gateway.acomplete_structured(
                [{"role": "user", "content": build_transcript_document_prompt(video, transcript)}],
                response_model=SummaryPayload,
            )
            summary_data = payload.model_dump()
            markdown = render_markdown(summary_data)
            return SummaryDocument(markdown=markdown, summary_data=summary_data)

        chunks = list(enumerate(chunk_segments(transcript.segments), start=1))
        chunk_summaries = await self._summarize_chunks(video, chunks)
        payload = await self._gateway.acomplete_structured(
            [{"role": "user", "content": build_document_prompt(video, transcript, chunk_summaries)}],
            response_model=SummaryPayload,
        )
        summary_data = payload.model_dump()
        markdown = render_markdown(summary_data)
        return SummaryDocument(markdown=markdown, summary_data=summary_data)

    async def _summarize_chunks(
        self,
        video: VideoAsset,
        chunks: list[tuple[int, list]],
    ) -> list[str]:
        semaphore = asyncio.Semaphore(self._summary_chunk_concurrency)

        async def summarize_chunk(index: int, chunk: list) -> tuple[int, str]:
            async with semaphore:
                summary = await self._gateway.acomplete_text(
                    [{"role": "user", "content": build_chunk_prompt(video, chunk, index)}]
                )
                return index, summary

        results = await asyncio.gather(
            *(summarize_chunk(index, chunk) for index, chunk in chunks)
        )
        return [summary for _, summary in sorted(results, key=lambda item: item[0])]


def _should_use_direct_summary(
    *,
    video: VideoAsset,
    transcript: Transcript,
    context_window_tokens: int,
    reserved_output_tokens: int,
    direct_summary_threshold_ratio: float,
) -> bool:
    available_tokens = max(1, context_window_tokens - reserved_output_tokens)
    direct_summary_budget = max(1, int(available_tokens * direct_summary_threshold_ratio))
    direct_prompt = build_transcript_document_prompt(video, transcript)
    return _estimate_tokens(direct_prompt) <= direct_summary_budget


def _estimate_tokens(value: str) -> int:
    text = value.strip()
    if not text:
        return 0
    return max(1, len(text.encode("utf-8")) // 3)
