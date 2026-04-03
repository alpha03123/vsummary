from __future__ import annotations

import json
from pathlib import Path

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
    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        self._gateway = OpenAIResponsesGateway(model=model, base_url=base_url, api_key=api_key)

    def summarize(self, video: VideoAsset, transcript: Transcript, output_dir: Path) -> SummaryDocument:
        chunk_summaries = [
            self._gateway.create_text(build_chunk_prompt(video, chunk, index))
            for index, chunk in enumerate(chunk_segments(transcript.segments), start=1)
        ]
        summary_data = parse_summary_payload(
            self._gateway.create_text(build_document_prompt(video, transcript, chunk_summaries)),
            video,
        )
        markdown = render_markdown(summary_data)

        (output_dir / "summary.md").write_text(markdown, encoding="utf-8")
        (output_dir / "summary.json").write_text(
            json.dumps(summary_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return SummaryDocument(markdown=markdown, summary_data=summary_data)
