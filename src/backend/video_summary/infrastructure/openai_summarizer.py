from __future__ import annotations

from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import Summarizer
from backend.video_summary.infrastructure.openai_summary import (
    OpenAIResponsesGateway,
    build_chunk_prompt,
    build_document_prompt,
    chunk_segments,
    parse_summary_payload,
    render_markdown,
)


class OpenAIResponsesClient(Summarizer):
    def __init__(self, gateway: OpenAIResponsesGateway) -> None:
        self._gateway = gateway

    async def summarize(self, video: VideoAsset, transcript: Transcript) -> SummaryDocument:
        chunk_summaries = [
            await self._gateway.create_text(build_chunk_prompt(video, chunk, index))
            for index, chunk in enumerate(chunk_segments(transcript.segments), start=1)
        ]
        summary_data = parse_summary_payload(
            await self._gateway.create_text(build_document_prompt(video, transcript, chunk_summaries)),
            video,
        )
        markdown = render_markdown(summary_data)
        return SummaryDocument(markdown=markdown, summary_data=summary_data)
