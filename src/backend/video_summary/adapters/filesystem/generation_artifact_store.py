from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.common.filesystem import atomic_write_text
from backend.video_summary.summary_generation.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.summary_generation.ports import GenerationArtifactStore


class FileSystemGenerationArtifactStore(GenerationArtifactStore):
    async def save_cleaned_transcript(
        self,
        *,
        video: VideoAsset,
        transcript: Transcript,
        output_dir: Path,
    ) -> None:
        payload = {
            "title": video.title,
            "language": transcript.language,
            "duration_seconds": video.duration_seconds,
            "segments": [
                {
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    "text": segment.text,
                }
                for segment in transcript.segments
            ],
        }
        await _write_json(output_dir / "transcript.cleaned.json", payload)

    async def save_enhanced_transcript(
        self,
        *,
        transcript: Transcript,
        output_dir: Path,
    ) -> None:
        payload = {
            "language": transcript.language,
            "segments": [
                {
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    "text": segment.text,
                }
                for segment in transcript.segments
            ],
        }
        await _write_json(output_dir / "transcript.enhanced.json", payload)

    async def save_summary_document(self, *, document: SummaryDocument, output_dir: Path) -> None:
        await asyncio.gather(
            _write_text(output_dir / "summary.md", document.markdown),
            _write_json(output_dir / "summary.json", document.summary_data),
        )

    async def save_mindmap(self, *, mindmap: dict[str, object], output_dir: Path) -> None:
        await _write_json(output_dir / "mindmap.json", mindmap)


async def _write_json(path: Path, payload: dict[str, object]) -> None:
    await _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


async def _write_text(path: Path, content: str) -> None:
    await asyncio.to_thread(_sync_write_text, path, content)


def _sync_write_text(path: Path, content: str) -> None:
    atomic_write_text(path, content)
