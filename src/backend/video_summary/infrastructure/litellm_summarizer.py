from __future__ import annotations

from backend.shared.llm import LiteLLMCompletionGateway
from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import Summarizer
from backend.video_summary.infrastructure.structured_generation import (
    SummaryPayload,
    build_chunk_prompt,
    build_document_prompt,
    chunk_segments,
    render_markdown,
)


class LiteLLMCompletionSummarizer(Summarizer):
    def __init__(self, gateway: LiteLLMCompletionGateway) -> None:
        self._gateway = gateway

    async def summarize(self, video: VideoAsset, transcript: Transcript) -> SummaryDocument:
        chunk_summaries = [
            await self._gateway.acomplete_text(
                [{"role": "user", "content": build_chunk_prompt(video, chunk, index)}]
            )
            for index, chunk in enumerate(chunk_segments(transcript.segments), start=1)
        ]
        payload = await self._gateway.acomplete_structured(
            [{"role": "user", "content": build_document_prompt(video, transcript, chunk_summaries)}],
            response_model=SummaryPayload,
        )
        summary_data = payload.model_dump()
        markdown = render_markdown(summary_data)
        return SummaryDocument(markdown=markdown, summary_data=summary_data)
