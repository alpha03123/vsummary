from __future__ import annotations

import unittest

from backend.video_summary.library.usecases.ai_notes import (
    AiSummaryImageCoverageError,
    count_ai_summary_sections,
    constrain_ai_note_image_markers,
    validate_ai_summary_image_coverage,
)


class AiNoteMarkerConstraintTests(unittest.TestCase):
    def test_allows_ai_image_markers_without_a_summary(self) -> None:
        content = constrain_ai_note_image_markers(
            "正文\n\n[[IMG:00:05]]",
            duration_seconds=10,
            enabled=True,
            max_images=1,
            min_gap_seconds=5,
        )

        self.assertIn("[[IMG:00:05]]", content)

    def test_keeps_out_of_duration_marker_for_the_renderer(self) -> None:
        content = constrain_ai_note_image_markers(
            "正文\n\n[[IMG:00:15]]\n\n[[IMG:00:05]]",
            duration_seconds=10,
            enabled=True,
            max_images=1,
            min_gap_seconds=5,
        )

        self.assertIn("[[IMG:00:15]]", content)
        self.assertIn("[[IMG:00:05]]", content)

    def test_requires_ninety_percent_coverage_of_numbered_sections(self) -> None:
        content = "\n".join(
            [f"## {index}. 章节 {index}\n正文\n[[IMG:{index * 10}]]" for index in range(1, 10)]
        )

        validate_ai_summary_image_coverage(
            content,
            duration_seconds=100,
            enabled=True,
            max_images=10,
        )

    def test_counts_only_top_level_markdown_sections(self) -> None:
        content = "## 1. 一级章节\n### 1.1 子标题\n```markdown\n## 代码块中的标题\n```\n## 2. 第二章"

        self.assertEqual(count_ai_summary_sections(content), 2)

    def test_caps_required_coverage_at_image_limit(self) -> None:
        content = "\n".join(
            [f"## {index}. 章节 {index}\n正文\n[[IMG:{index * 10}]]" for index in range(1, 11)]
        )

        validate_ai_summary_image_coverage(
            content,
            duration_seconds=120,
            enabled=True,
            max_images=9,
        )

        with self.assertRaises(AiSummaryImageCoverageError):
            validate_ai_summary_image_coverage(
                content.replace("[[IMG:90]]", "").replace("[[IMG:100]]", ""),
                duration_seconds=120,
                enabled=True,
                max_images=9,
            )


if __name__ == "__main__":
    unittest.main()
