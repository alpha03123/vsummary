from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


from backend.api.responses import VideoKnowledgeCardsResponse
from backend.video_summary.infrastructure.filesystem_video_workspace import FileSystemVideoWorkspace
from backend.video_summary.infrastructure.litellm_mindmap_generator import build_mindmap_prompt
from backend.video_summary.infrastructure.litellm_series_mindmap_generator import build_series_mindmap_prompt
from backend.video_summary.library.models import KnowledgeCardDTO, VideoKnowledgeCardsDTO


class MindmapPromptTests(unittest.TestCase):
    def test_prompt_allows_depth_to_follow_content_complexity(self) -> None:
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={
                "title": "测试视频",
                "chapters": [
                    {
                        "id": "chapter-1",
                        "title": "章节一",
                        "summary": "章节摘要",
                        "key_points": ["要点一"],
                        "start_seconds": 0.0,
                        "end_seconds": 120.0,
                    }
                ],
            },
        )

        self.assertIn("层级深度由内容复杂度决定", prompt)
        self.assertNotIn("二三级节点用于展开要点", prompt)


class SeriesMindmapPromptTests(unittest.TestCase):
    def test_prompt_includes_series_catalog_and_video_summaries(self) -> None:
        prompt = build_series_mindmap_prompt(
            series_title="测试系列",
            catalog={"videos": [{"id": "v1", "title": "第一讲"}]},
            video_summaries=[
                {
                    "title": "第一讲",
                    "one_sentence_summary": "介绍核心概念。",
                    "chapters": [{"title": "核心概念"}],
                }
            ],
        )

        self.assertIn("测试系列", prompt)
        self.assertIn("第一讲", prompt)
        self.assertIn("介绍核心概念", prompt)
        self.assertIn("按知识主题组织二级节点", prompt)


class LLMKnowledgeCardGeneratorTests(unittest.TestCase):
    def test_generator_uses_transcript_context_and_returns_explanatory_cards(self) -> None:
        from backend.video_summary.infrastructure.litellm_knowledge_card_generator import (
            KnowledgeCardCollectionPayload,
            LiteLLMKnowledgeCardGenerator,
        )

        gateway = FakeKnowledgeCardGateway()
        generator = LiteLLMKnowledgeCardGenerator(gateway)

        cards = generator.run(
            title="多 Agent 课程",
            summary_data={
                "title": "多 Agent 课程",
                "chapters": [
                    {
                        "id": "chapter-1",
                        "title": "Agent 协作",
                        "summary": "讲解多 Agent 如何分工协作。",
                        "key_points": ["多个 Agent 分工", "协调机制"],
                        "start_seconds": 0.0,
                        "end_seconds": 100.0,
                        "transcript_segments": [
                            {
                                "start_seconds": 0.0,
                                "end_seconds": 12.0,
                                "text": "多个 Agent 不是简单并行，而是围绕共享目标协作。",
                            }
                        ],
                    }
                ],
                "key_takeaways": ["多 Agent 的关键是协作而不是堆数量。"],
            },
        )

        self.assertEqual(len(cards), 2)
        self.assertTrue(all(isinstance(card, KnowledgeCardDTO) for card in cards))
        self.assertIn("多个 Agent 不是简单并行", gateway.messages[0][0]["content"])
        self.assertEqual(cards[0].title, "多 Agent 协作")
        self.assertEqual(cards[0].kind, "concept")
        self.assertEqual(cards[1].kind, "insight")


class KnowledgeCardWorkspaceCompatibilityTests(unittest.TestCase):
    def test_workspace_accepts_cards_without_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            series_dir = root_dir / "videos" / "series-1"
            series_dir.mkdir(parents=True)
            (series_dir / "video-1.mp4").write_bytes(b"")

            output_dir = root_dir / "workspace" / "series-1" / "video-1"
            output_dir.mkdir(parents=True)
            (output_dir / "knowledge_cards.json").write_text(
                json.dumps(
                    {
                        "title": "测试视频",
                        "cards": [
                            {
                                "id": "kc-1",
                                "title": "反常识协作",
                                "kind": "insight",
                                "summary": "协作的关键不是数量，而是清晰分工。",
                                "details": "当多个 Agent 没有边界时，只会放大噪音。",
                                "tags": ["多 Agent", "协作"],
                                "keywords": ["协作", "分工"],
                                "related_card_ids": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            workspace = FileSystemVideoWorkspace(root_dir)

            cards = workspace.get_video_knowledge_cards("series-1", "video-1")

            self.assertIsNotNone(cards)
            self.assertEqual(cards.cards[0].kind, "insight")
            self.assertFalse(hasattr(cards.cards[0], "source_refs"))


class KnowledgeCardResponseTests(unittest.TestCase):
    def test_api_response_omits_source_refs(self) -> None:
        response = VideoKnowledgeCardsResponse.from_model(
            VideoKnowledgeCardsDTO(
                series_id="series-1",
                video_id="video-1",
                title="测试视频",
                cards=[
                    KnowledgeCardDTO(
                        id="kc-1",
                        title="多 Agent 协作",
                        kind="concept",
                        summary="多个智能体围绕共享目标协作。",
                        details="它要求目标一致、边界清晰、协调顺畅，否则数量只会放大噪音。",
                        tags=["多 Agent"],
                        keywords=["协作"],
                        related_card_ids=[],
                    )
                ],
            )
        )

        self.assertNotIn("source_refs", response.model_dump()["cards"][0])


class FakeKnowledgeCardGateway:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def complete_structured(self, messages, *, response_model, temperature=0, retries=2):
        del response_model, temperature, retries
        from backend.video_summary.infrastructure.litellm_knowledge_card_generator import (
            KnowledgeCardCollectionPayload,
        )

        self.messages.append(list(messages))
        return KnowledgeCardCollectionPayload(
            cards=[
                {
                    "id": "kc-1",
                    "title": "多 Agent 协作",
                    "kind": "concept",
                    "summary": "多 Agent 协作指多个智能体围绕同一目标进行分工与配合。",
                    "details": "它强调目标一致、边界清晰和信息传递，而不是单纯增加执行单元数量。",
                    "tags": ["多 Agent", "协作"],
                    "keywords": ["多Agent", "协作", "分工"],
                },
                {
                    "id": "kc-2",
                    "title": "协作比数量更重要",
                    "kind": "insight",
                    "summary": "Agent 数量增加并不自动带来效果提升，协作结构才是关键变量。",
                    "details": "如果缺少清晰分工和协调机制，更多 Agent 只会制造重复劳动和额外噪音。",
                    "tags": ["多 Agent", "洞见"],
                    "keywords": ["数量", "协作", "协调"],
                },
            ]
        )


if __name__ == "__main__":
    unittest.main()
