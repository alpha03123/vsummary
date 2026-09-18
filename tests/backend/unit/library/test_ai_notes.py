from __future__ import annotations

import unittest

from backend.video_summary.library.usecases.ai_notes import constrain_ai_note_image_markers


class AiNoteMarkerConstraintTests(unittest.TestCase):
    def test_allows_ai_image_markers_without_a_summary(self) -> None:
        content = constrain_ai_note_image_markers(
            "正文\n\n[[IMG:00:05]]",
            summary=None,
            duration_seconds=10,
            enabled=True,
            max_images=1,
            min_gap_seconds=5,
        )

        self.assertIn("[[IMG:00:05]]", content)

    def test_keeps_out_of_duration_marker_for_the_renderer(self) -> None:
        content = constrain_ai_note_image_markers(
            "正文\n\n[[IMG:00:15]]\n\n[[IMG:00:05]]",
            summary=None,
            duration_seconds=10,
            enabled=True,
            max_images=1,
            min_gap_seconds=5,
        )

        self.assertIn("[[IMG:00:15]]", content)
        self.assertIn("[[IMG:00:05]]", content)


if __name__ == "__main__":
    unittest.main()
