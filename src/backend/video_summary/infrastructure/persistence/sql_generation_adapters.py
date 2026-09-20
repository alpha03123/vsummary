"""将现有生成工作流的临时文件结果发布到 SQL。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from backend.core.citations import CitationReference
from backend.video_summary.domain.models import ManualTranscriptInput
from backend.video_summary.generation.ports import ProgressReporter
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace
from backend.video_summary.infrastructure.video_summary_workflow import ConfiguredVideoSummaryWorkflow
from backend.video_summary.infrastructure.mindmap_workflow import ConfiguredMindmapWorkflow
from backend.video_summary.infrastructure.series_mindmap_workflow import ConfiguredSeriesMindmapWorkflow


class SqlBackedVideoSummaryGenerator:
    """运行既有工作流到临时目录，再发布其 JSON 结果到 SQL。"""

    def __init__(self, *, workspace: SqlVideoWorkspace, workflow: ConfiguredVideoSummaryWorkflow, temp_root: Path) -> None:
        self._workspace = workspace
        self._workflow = workflow
        self._temp_root = temp_root

    async def run(
        self,
        *,
        series_id: str,
        video_id: str,
        progress_reporter: ProgressReporter | None = None,
        transcript_enhancement_enabled: bool | None = None,
        manual_transcript: ManualTranscriptInput | None = None,
        use_saved_manual_transcript: bool = True,
        processing_mode: str = "summary",
        job_id: str | None = None,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> None:
        source = self._workspace.get_video_source(series_id, video_id)
        if source is None:
            raise LookupError(f"video not found '{series_id}/{video_id}'")
        output_dir = self._temp_root / "generation" / video_id / uuid4().hex
        try:
            await self._workflow.run(source.source_path, output_dir, progress_reporter=progress_reporter, transcript_enhancement_enabled=transcript_enhancement_enabled, manual_transcript=manual_transcript, use_saved_manual_transcript=use_saved_manual_transcript, processing_mode=processing_mode)
            transcript_path = output_dir / "transcript.cleaned.json"
            summary_path = output_dir / "summary.json"
            if not transcript_path.is_file() or not summary_path.is_file():
                raise RuntimeError("Generation completed without transcript and summary artifacts.")
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            payload = {
                "transcript": {
                    "language": str(transcript.get("language") or "und"),
                    "source_type": "generated",
                    "duration_ms": round(float(transcript.get("duration_seconds") or 0) * 1000),
                    "segments": [
                        {"start_ms": round(float(item["start_seconds"]) * 1000), "end_ms": round(float(item["end_seconds"]) * 1000), "text": str(item["text"])}
                        for item in transcript.get("segments", []) if isinstance(item, dict)
                    ],
                },
                "summary": {
                    "title": str(summary.get("title") or source.title),
                    "markdown": (output_dir / "summary.md").read_text(encoding="utf-8") if (output_dir / "summary.md").is_file() else "",
                    "payload": summary,
                    "chapters": _chapters(summary),
                },
            }
            if job_id is None:
                self._workspace._publish_manual_content(series_id, video_id, payload, "generate")
            else:
                if not worker_id or not lease_token:
                    raise ValueError("Worker-owned generation requires worker_id and lease_token.")
                self._workspace.publish_generated_content(
                    series_id=series_id,
                    video_id=video_id,
                    job_id=job_id,
                    worker_id=worker_id,
                    lease_token=lease_token,
                    payload=payload,
                )
            for image in (output_dir / "screenshots").glob("*.jpg") if (output_dir / "screenshots").is_dir() else []:
                self._workspace.save_binary_artifact(video_id=video_id, kind="screenshot", source_path=image)
            for image in (output_dir / "frames").glob("*.jpg") if (output_dir / "frames").is_dir() else []:
                self._workspace.save_binary_artifact(video_id=video_id, kind="note_frame", source_path=image)
            ai_summary_path = output_dir / "ai_summary.json"
            if ai_summary_path.is_file():
                ai_summary = json.loads(ai_summary_path.read_text(encoding="utf-8"))
                self._workspace.save_video_ai_summary(
                    series_id,
                    video_id,
                    title=str(ai_summary.get("title") or source.title),
                    content=str(ai_summary.get("content") or ""),
                    citations=[
                        CitationReference.model_validate(item)
                        for item in ai_summary.get("citations", [])
                        if isinstance(item, dict)
                    ],
                )
                evidence_path = output_dir / "ai_summary.visual_evidence.json"
                if evidence_path.is_file():
                    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                    from backend.video_summary.library.models import AiSummaryVisualEvidenceDTO

                    self._workspace.save_video_ai_summary_visual_evidence(
                        series_id,
                        video_id,
                        frames=[
                            AiSummaryVisualEvidenceDTO(
                                timestamp_seconds=float(item["timestamp_seconds"]),
                                text=str(item["text"]),
                            )
                            for item in evidence.get("frames", [])
                            if isinstance(item, dict)
                            and isinstance(item.get("timestamp_seconds"), (int, float))
                            and isinstance(item.get("text"), str)
                            and item["text"].strip()
                        ],
                    )
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)


class SqlBackedVideoMindmapGenerator:
    """保留既有 LLM 导图生成，最终只把临时 JSON 发布至 SQL。"""

    def __init__(self, *, workspace: SqlVideoWorkspace, workflow: ConfiguredMindmapWorkflow, temp_root: Path) -> None:
        self._workspace = workspace
        self._workflow = workflow
        self._temp_root = temp_root

    async def run(self, *, series_id: str, video_id: str, summary_data: dict[str, object], transcript_text: str = "", visual_evidence_text: str = "", visual_frame_paths=None, progress_reporter=None, max_depth: int | None = None) -> None:
        source = self._workspace.get_video_source(series_id, video_id)
        if source is None:
            raise LookupError(f"video not found '{series_id}/{video_id}'")
        output_dir = self._temp_root / "mindmap" / video_id / uuid4().hex
        try:
            await self._workflow.run(source.source_path, output_dir, summary_data, transcript_text=transcript_text, visual_evidence_text=visual_evidence_text, visual_frame_paths=visual_frame_paths, progress_reporter=progress_reporter, max_depth=max_depth)
            path = output_dir / "mindmap.json"
            if not path.is_file():
                raise RuntimeError("Mindmap generation completed without a mindmap artifact.")
            self._workspace.save_video_mindmap(series_id, video_id, mindmap=json.loads(path.read_text(encoding="utf-8")))
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)


class SqlBackedSeriesMindmapGenerator:
    """系列导图工作流仅使用临时目录，最终结果写入 SQL。"""

    def __init__(self, *, workspace: SqlVideoWorkspace, workflow: ConfiguredSeriesMindmapWorkflow, temp_root: Path) -> None:
        self._workspace = workspace
        self._workflow = workflow
        self._temp_root = temp_root

    async def run(self, *, series_id: str, series_title: str, catalog: dict[str, object] | None, video_summaries: list[dict[str, object]], progress_reporter=None, max_depth: int | None = None) -> None:
        output_dir = self._temp_root / "series-mindmap" / series_id / uuid4().hex
        try:
            await self._workflow.run(output_dir, series_title, catalog, video_summaries, progress_reporter=progress_reporter, max_depth=max_depth)
            path = output_dir / "mindmap.json"
            if not path.is_file():
                raise RuntimeError("Series mindmap generation completed without a mindmap artifact.")
            self._workspace.save_series_mindmap(series_id, mindmap=json.loads(path.read_text(encoding="utf-8")))
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)


def _chapters(summary: dict[str, object]) -> list[dict[str, object]]:
    result = []
    for item in summary.get("chapters", []) if isinstance(summary.get("chapters"), list) else []:
        if isinstance(item, dict):
            result.append({"title": str(item.get("title") or "Untitled"), "start_ms": round(float(item["start_seconds"]) * 1000) if isinstance(item.get("start_seconds"), (int, float)) else None, "end_ms": round(float(item["end_seconds"]) * 1000) if isinstance(item.get("end_seconds"), (int, float)) else None, "body": str(item.get("summary") or ""), "payload": item})
    return result
