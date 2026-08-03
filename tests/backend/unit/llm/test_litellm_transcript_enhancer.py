from __future__ import annotations

import unittest
from pathlib import Path

from backend.video_summary.domain.models import TranscriptSegment, VideoAsset
from backend.video_summary.infrastructure.llm.litellm_transcript_enhancer import (
    _build_transcript_enhancement_prompt,
)


class TranscriptEnhancementPromptTests(unittest.TestCase):
    def test_marks_english_transcript_as_english(self) -> None:
        prompt = _build_transcript_enhancement_prompt(
            VideoAsset(Path("video.mp4"), "English video", 1.0),
            "en",
            [TranscriptSegment(0.0, 1.0, "English transcript")],
            1,
            1,
        )

        self.assertIn("纠正EN视频转写文本", prompt)
        self.assertNotIn("纠正中文视频转写文本", prompt)

    def test_marks_chinese_transcript_as_chinese(self) -> None:
        prompt = _build_transcript_enhancement_prompt(
            VideoAsset(Path("video.mp4"), "中文视频", 1.0),
            "zh",
            [TranscriptSegment(0.0, 1.0, "中文转写")],
            1,
            1,
        )

        self.assertIn("纠正中文视频转写文本", prompt)

    def test_auto_language_preserves_the_recognized_language(self) -> None:
        prompt = _build_transcript_enhancement_prompt(
            VideoAsset(Path("video.mp4"), "Auto video", 1.0),
            "auto",
            [TranscriptSegment(0.0, 1.0, "Transcript")],
            1,
            1,
        )

        self.assertIn("纠正原始识别语言视频转写文本", prompt)
        self.assertIn("保持原始语言，不要翻译", prompt)
