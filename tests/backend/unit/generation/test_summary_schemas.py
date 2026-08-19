from __future__ import annotations

import unittest

from pydantic import ValidationError

from backend.video_summary.generation.schemas import SummaryPayload


class SummarySchemaTests(unittest.TestCase):
    def test_rejects_non_finite_chapter_timestamps(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            SummaryPayload.model_validate(
                {
                    "title": "概况",
                    "chapters": [
                        {"id": "chapter-1", "title": "第一章", "start_seconds": float("nan"), "end_seconds": 10},
                    ],
                }
            )

        self.assertIn("finite number", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
