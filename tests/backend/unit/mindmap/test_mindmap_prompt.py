from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.litellm_mindmap_generator import build_mindmap_prompt


class MindmapPromptTranscriptTests(unittest.TestCase):
    def test_prompt_includes_transcript_text(self) -> None:
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试", "chapters": []},
            transcript_text="这是一段转写文本",
        )
        self.assertIn("转写文本", prompt)
        self.assertIn("这是一段转写文本", prompt)

    def test_prompt_handles_empty_transcript(self) -> None:
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试", "chapters": []},
            transcript_text="",
        )
        self.assertIn("转写文本", prompt)

    def test_prompt_truncates_long_transcript(self) -> None:
        long_text = "测" * 10000
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试", "chapters": []},
            transcript_text=long_text,
        )
        transcript_start = prompt.find("转写文本：") + len("转写文本：")
        transcript_section = prompt[transcript_start:].strip()
        self.assertLessEqual(len(transcript_section), 3000)

    def test_prompt_still_includes_summary_and_title(self) -> None:
        prompt = build_mindmap_prompt(
            title="测试视频",
            duration_seconds=300.0,
            summary_data={"title": "测试视频", "chapters": []},
            transcript_text="转写内容",
        )
        self.assertIn("测试视频", prompt)
        self.assertIn("300", prompt)


if __name__ == "__main__":
    unittest.main()
