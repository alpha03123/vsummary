from __future__ import annotations

import unittest

from backend.video_summary.library.markdown_exports import render_knowledge_cards_markdown
from backend.video_summary.library.markdown_exports import render_notes_markdown
from backend.video_summary.library.markdown_exports import render_transcript_markdown


class MarkdownExportTests(unittest.TestCase):
    def test_renders_transcript_segments_as_markdown_with_metadata(self) -> None:
        markdown = render_transcript_markdown(
            {
                "title": "第一讲",
                "language": "zh",
                "duration_seconds": 65.0,
                "segments": [
                    {"start_seconds": 0.0, "end_seconds": 3.5, "text": "开场介绍"},
                    {"start_seconds": 3.5, "end_seconds": 65.0, "text": "进入主题"},
                ],
            }
        )

        self.assertIn("# 第一讲 转写稿\n", markdown)
        self.assertIn("- 语言：zh\n", markdown)
        self.assertIn("- 时长：01:05\n", markdown)
        self.assertIn("### 00:00 - 00:03\n开场介绍\n", markdown)
        self.assertIn("### 00:03 - 01:05\n进入主题\n", markdown)

    def test_rejects_invalid_transcript_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "segments 必须是数组"):
            render_transcript_markdown({"title": "第一讲", "segments": "bad"})

    def test_renders_knowledge_cards_as_markdown(self) -> None:
        markdown = render_knowledge_cards_markdown(
            {
                "title": "第一讲",
                "cards": [
                    {
                        "id": "card-1",
                        "title": "冷启动",
                        "kind": "method",
                        "summary": "先解决曝光问题。",
                        "details": "围绕目标用户正在关注的话题发布内容。",
                        "tags": ["增长", "产品"],
                        "keywords": ["曝光"],
                        "related_card_ids": [],
                    }
                ],
            }
        )

        self.assertIn("# 第一讲 知识卡片\n", markdown)
        self.assertIn("## 冷启动\n", markdown)
        self.assertIn("- 类型：method\n", markdown)
        self.assertIn("- 标签：增长、产品\n", markdown)
        self.assertIn("- 关键词：曝光\n", markdown)
        self.assertIn("### 摘要\n先解决曝光问题。\n", markdown)
        self.assertIn("### 详情\n围绕目标用户正在关注的话题发布内容。\n", markdown)

    def test_rejects_invalid_knowledge_card_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "cards 必须是数组"):
            render_knowledge_cards_markdown({"title": "第一讲", "cards": None})

    def test_renders_notes_as_markdown(self) -> None:
        markdown = render_notes_markdown(
            "第一讲",
            {
                "notes": [
                    {
                        "id": "note-1",
                        "title": "重点",
                        "content": "这里是 **Markdown** 笔记。",
                        "source": "manual",
                        "created_at": "2026-06-06T10:00:00Z",
                        "updated_at": "2026-06-06T10:30:00Z",
                    }
                ],
            },
        )

        self.assertIn("# 第一讲 笔记\n", markdown)
        self.assertIn("## 重点\n", markdown)
        self.assertIn("- 来源：manual\n", markdown)
        self.assertIn("- 创建时间：2026-06-06T10:00:00Z\n", markdown)
        self.assertIn("- 更新时间：2026-06-06T10:30:00Z\n", markdown)
        self.assertIn("这里是 **Markdown** 笔记。\n", markdown)

    def test_rejects_invalid_notes_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "notes 必须是数组"):
            render_notes_markdown("第一讲", {"notes": "bad"})


if __name__ == "__main__":
    unittest.main()
