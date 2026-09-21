from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.llm.prompts.notes import build_ai_note_prompt


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
        self.assertIn("不要反复使用「要点」", prompt)
        self.assertNotIn("`**要点**：说明`", prompt)


if __name__ == "__main__":
    unittest.main()
