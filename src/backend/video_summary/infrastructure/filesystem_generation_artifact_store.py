"""把生成阶段的制品（转写/总结/思维导图）落盘到工作区的 `GenerationArtifactStore` 实现。

所有写盘都通过 `backend.shared.filesystem.atomic_write_text` 完成，确保在写
入过程中断也不会留下半截 JSON/Markdown；同时把同步磁盘 IO 卸载到线程池，
避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.shared.filesystem import atomic_write_text
from backend.video_summary.domain.models import SummaryDocument, Transcript, VideoAsset
from backend.video_summary.generation.ports import GenerationArtifactStore


class FileSystemGenerationArtifactStore(GenerationArtifactStore):
    """单视频生成期间所有"可观察制品"的本地文件落地器。

    输出目录约定（每个视频一个目录）：
        - `transcript.cleaned.json`：ASR 清理后的转写；
        - `transcript.enhanced.json`：经过 LLM 增强后的转写（可选）；
        - `summary.md` + `summary.json`：总结的 Markdown 与结构化数据；
        - `mindmap.json`：思维导图 JSON。
    """

    async def save_cleaned_transcript(
        self,
        *,
        video: VideoAsset,
        transcript: Transcript,
        output_dir: Path,
    ) -> None:
        """把 ASR 清理后的转写写入 `transcript.cleaned.json`。

        包含视频标题、语言、时长与每段的起止时间/文本。
        """
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
        """把 LLM 增强后的转写写入 `transcript.enhanced.json`（仅含语言与分段）。"""
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
        """把总结文档同时写到 `summary.md`（可读）与 `summary.json`（结构化）。

        两个文件并发写，避免总结被部分写入时两边不一致（同一份数据）。
        """
        await asyncio.gather(
            _write_text(output_dir / "summary.md", document.markdown),
            _write_json(output_dir / "summary.json", document.summary_data),
        )

    async def save_mindmap(self, *, mindmap: dict[str, object], output_dir: Path) -> None:
        """把思维导图 JSON 写入 `mindmap.json`。"""
        await _write_json(output_dir / "mindmap.json", mindmap)


async def _write_json(path: Path, payload: dict[str, object]) -> None:
    """把 dict 用 `ensure_ascii=False` 序列化后写入目标路径（走原子写）。"""
    await _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


async def _write_text(path: Path, content: str) -> None:
    """在线程池中执行磁盘写，避免阻塞事件循环。"""
    await asyncio.to_thread(_sync_write_text, path, content)


def _sync_write_text(path: Path, content: str) -> None:
    """真正执行原子写（`backend.shared.filesystem.atomic_write_text`）。"""
    atomic_write_text(path, content)
