"""生成任务临时目录的 artifact writer。

这些 JSON/Markdown/SRT 文件只在模型、FFmpeg 与现有生成用例之间交换。
`SqlBacked*Generator` 成功解析后会将内容提交到 MySQL/BlobStore 并删除整个
临时目录；它们绝不是用户业务数据的持久化格式。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.domain.models import ManualTranscriptInput, SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import GenerationArtifactStore
from backend.video_summary.generation.schemas import VisualEvidencePayload


class TemporaryGenerationArtifactStore(GenerationArtifactStore):
    async def save_cleaned_transcript(self, *, video: VideoAsset, transcript: Transcript, output_dir: Path) -> None:
        await _write_json(output_dir / "transcript.cleaned.json", {"title": video.title, "language": transcript.language, "duration_seconds": video.duration_seconds, "segments": [{"start_seconds": item.start_seconds, "end_seconds": item.end_seconds, "text": item.text} for item in transcript.segments]})

    async def save_enhanced_transcript(self, *, transcript: Transcript, output_dir: Path) -> None:
        await _write_json(output_dir / "transcript.enhanced.json", {"language": transcript.language, "segments": [{"start_seconds": item.start_seconds, "end_seconds": item.end_seconds, "text": item.text} for item in transcript.segments]})

    async def save_manual_transcript(self, *, manual_transcript: ManualTranscriptInput, output_dir: Path) -> None:
        await asyncio.gather(_write_text(output_dir / "transcript.manual.srt", manual_transcript.raw_srt), _write_json(output_dir / "transcript.source.json", {"source": "manual_srt", "filename": manual_transcript.filename}))

    async def save_summary_document(self, *, document: SummaryDocument, output_dir: Path) -> None:
        await asyncio.gather(_write_text(output_dir / "summary.md", document.markdown), _write_json(output_dir / "summary.json", document.summary_data))

    async def save_visual_evidence(self, *, evidence: VisualEvidencePayload, output_dir: Path) -> None:
        await _write_json(output_dir / "visual.evidence.json", evidence.model_dump(mode="json"))

    async def save_mindmap(self, *, mindmap: dict[str, object], output_dir: Path) -> None:
        await _write_json(output_dir / "mindmap.json", mindmap)


async def _write_json(path: Path, payload: dict[str, object]) -> None:
    await _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


async def _write_text(path: Path, content: str) -> None:
    await asyncio.to_thread(atomic_write_text, path, content)
