from __future__ import annotations

import unittest

from backend.agent_graph.prompts.notes import build_ai_note_prompt


class AiNotePromptTests(unittest.TestCase):
    def test_includes_selected_template_and_transcript(self) -> None:
        prompt = build_ai_note_prompt(
            title="视频标题",
            transcript_text="00:00 - 重点内容",
            template="tutorial",
        )

        self.assertIn("笔记风格：操作教程", prompt)
        self.assertIn("00:00 - 重点内容", prompt)
        self.assertIn("只输出最终 Markdown", prompt)


if __name__ == "__main__":
    unittest.main()
