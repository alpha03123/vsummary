from __future__ import annotations

from dataclasses import replace
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from llama_index.core.embeddings import MockEmbedding

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.evidence.retrieval import (
    SeriesRetrievalService,
    _build_default_embed_model,
    _build_workspace_signature,
)
from backend.video_summary.library.views import (
    KnowledgeCardSourceRefView,
    KnowledgeCardView,
    SeriesView,
    TranscriptSegmentView,
    VideoCardView,
    VideoNoteView,
    VideoNotesView,
    VideoSummaryView,
    VideoTranscriptView,
    VideoKnowledgeCardsView,
)


class _FakeWorkspace:
    def list_series(self):
        return [
            SeriesView(
                id="series-a",
                title="Series A",
                videos=[
                    VideoCardView(id="video-1", title="Video 1", source_name="video-1.mp4", processed=True, status="ready"),
                    VideoCardView(id="video-2", title="Video 2", source_name="video-2.mp4", processed=True, status="ready"),
                ],
            )
        ]

    def get_video_summary(self, series_id: str, video_id: str):
        del series_id
        if video_id != "video-1":
            return None
        return VideoSummaryView(
            series_id="series-a",
            video_id="video-1",
            title="Video 1",
            summary={
                "one_sentence_summary": "这一节介绍 Nacos 3 的用途。",
                "core_problem": "服务发现",
                "key_takeaways": ["Nacos 3 是课程准备工作之一"],
                "chapters": [],
            },
        )

    def get_video_transcript(self, series_id: str, video_id: str):
        del series_id
        if video_id != "video-1":
            return None
        return VideoTranscriptView(
            series_id="series-a",
            video_id="video-1",
            title="Video 1",
            duration_seconds=100.0,
            segments=[
                TranscriptSegmentView(start_seconds=10.0, end_seconds=20.0, text="这里介绍 Nacos 3 的安装。")
            ],
        )

    def get_video_notes(self, series_id: str, video_id: str):
        del series_id
        if video_id != "video-1":
            return None
        return VideoNotesView(
            series_id="series-a",
            video_id="video-1",
            title="Video 1",
            notes=[
                VideoNoteView(
                    id="note-1",
                    title="OpenManus 重点",
                    content="这里提到 OpenManus 是开源框架。",
                    source="agent",
                    created_at="2026-04-19T00:00:00+00:00",
                    updated_at="2026-04-19T00:00:00+00:00",
                )
            ],
        )

    def get_video_knowledge_cards(self, series_id: str, video_id: str):
        del series_id
        if video_id != "video-1":
            return None
        return VideoKnowledgeCardsView(
            series_id="series-a",
            video_id="video-1",
            title="Video 1",
            cards=[
                KnowledgeCardView(
                    id="card-1",
                    title="OpenManus",
                    kind="concept",
                    summary="OpenManus 是开源框架。",
                    details="Spring AI Alibaba 基于 OpenManus 的思路扩展。",
                    tags=["framework"],
                    keywords=["openmanus"],
                    source_refs=[
                        KnowledgeCardSourceRefView(
                            chapter_id=None,
                            start_seconds=10.0,
                            end_seconds=20.0,
                            quote="这里介绍 OpenManus。",
                        )
                    ],
                    related_card_ids=[],
                )
            ],
        )


class _MutableWorkspace(_FakeWorkspace):
    def __init__(self) -> None:
        self.summary_text = "这一节介绍 Nacos 3 的用途。"
        self.transcript_text = "这里介绍 Nacos 3 的安装。"

    def get_video_summary(self, series_id: str, video_id: str):
        summary = super().get_video_summary(series_id, video_id)
        if summary is None:
            return None
        payload = dict(summary.summary)
        payload["one_sentence_summary"] = self.summary_text
        return replace(summary, summary=payload)

    def get_video_transcript(self, series_id: str, video_id: str):
        transcript = super().get_video_transcript(series_id, video_id)
        if transcript is None:
            return None
        segments = [
            replace(segment, text=self.transcript_text)
            for segment in transcript.segments
        ]
        return replace(transcript, segments=segments)


class AgentGraphRetrievalTests(unittest.TestCase):
    def test_default_embed_model_uses_local_huggingface_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir(parents=True)
            (root / "config" / "settings.toml").write_text(
                """
[asr]
provider = "faster_whisper"
language = "zh"
transcript_enhancement_enabled = true

[asr.faster_whisper]
device = "auto"
model_size = "small"
compute_type = "int8"
transcription_mode = "fast"

[agent_retrieval]
embedding_provider = "local_huggingface"
embedding_model = "BAAI/bge-base-zh-v1.5"
embedding_device = "cpu"
embedding_batch_size = 8
                """.strip(),
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "\n".join(
                    [
                        "OPENAI_PROVIDER=openai_compatible",
                        "OPENAI_BASE_URL=http://127.0.0.1:8317/v1",
                        "OPENAI_MODEL=gpt-5.4",
                        "OPENAI_API_KEY=test-key",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            fake_embedding = object()
            with patch(
                "backend.agent_graph.evidence.retrieval._build_local_huggingface_embedding",
                return_value=fake_embedding,
            ) as builder:
                result = _build_default_embed_model(root)

            self.assertIs(result, fake_embedding)
            retrieval_settings = builder.call_args.args[0]
            self.assertEqual(retrieval_settings.embedding_model, "BAAI/bge-base-zh-v1.5")

    def test_series_retrieval_service_dispatches_to_lancedb_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(
                workspace=_FakeWorkspace(),
                db_uri=str(Path(temp_dir) / "lancedb"),
                embed_model=MockEmbedding(embed_dim=32),
            )

            result = service.search(
                scope_type="series",
                series_id="series-a",
                video_id="",
                query="哪里讲过 Nacos 3？",
                target_source="transcript",
                expand_context=False,
                context_window_seconds=120,
                max_hits=5,
            )

            self.assertEqual(result["series_id"], "series-a")
            self.assertEqual(result["hits"][0]["video_id"], "video-1")
            self.assertEqual(result["hits"][0]["source_type"], "transcript_chunk")

    def test_video_retrieval_service_filters_to_requested_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(
                workspace=_FakeWorkspace(),
                db_uri=str(Path(temp_dir) / "lancedb"),
                embed_model=MockEmbedding(embed_dim=32),
            )

            result = service.search(
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
                query="Nacos 3",
                target_source="summary",
                expand_context=False,
                context_window_seconds=120,
                max_hits=5,
            )

            self.assertEqual(result["video_id"], "video-1")
            self.assertTrue(all(hit["video_id"] == "video-1" for hit in result["hits"]))

    def test_video_retrieval_service_can_search_notes_and_cards_by_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SeriesRetrievalService(
                workspace=_FakeWorkspace(),
                db_uri=str(Path(temp_dir) / "lancedb"),
                embed_model=MockEmbedding(embed_dim=32),
            )

            notes_result = service.search(
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
                query="OpenManus 是什么",
                target_source="all",
                source_tags=["notes"],
                expand_context=False,
                context_window_seconds=120,
                max_hits=5,
            )
            cards_result = service.search(
                scope_type="video",
                series_id="series-a",
                video_id="video-1",
                query="OpenManus 是什么",
                target_source="all",
                source_tags=["cards"],
                expand_context=False,
                context_window_seconds=120,
                max_hits=5,
            )

            self.assertEqual(notes_result["hits"][0]["source_type"], "note")
            self.assertEqual(cards_result["hits"][0]["source_type"], "knowledge_card")

    def test_workspace_signature_changes_when_summary_changes(self) -> None:
        workspace = _MutableWorkspace()
        before = _build_workspace_signature(workspace)

        workspace.summary_text = "这一节详细解释 Nacos 3 的服务发现链路。"
        after = _build_workspace_signature(workspace)

        self.assertNotEqual(before, after)

    def test_workspace_signature_changes_when_transcript_changes(self) -> None:
        workspace = _MutableWorkspace()
        before = _build_workspace_signature(workspace)

        workspace.transcript_text = "这里开始讲 Spring AI Alibaba 的接入流程。"
        after = _build_workspace_signature(workspace)

        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
