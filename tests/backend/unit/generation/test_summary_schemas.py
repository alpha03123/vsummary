from __future__ import annotations

import unittest

from pydantic import ValidationError

from backend.video_summary.generation.schemas import SummaryPayload


class SummarySchemaTests(unittest.TestCase):
    def test_rejects_overlapping_or_out_of_order_chapters(self) -> None:
        for start, end in [(9, 20), (0, 5)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValidationError):
                SummaryPayload.model_validate({
                    "title": "概况", "chapters": [
                        {"id": "chapter-1", "title": "第一章", "start_seconds": 0, "end_seconds": 10},
                        {"id": "chapter-2", "title": "第二章", "start_seconds": start, "end_seconds": end},
                    ],
                })

    def test_accepts_a_shared_boundary_without_overlapping_chapters(self) -> None:
        result = SummaryPayload.model_validate({
            "title": "概况", "chapters": [
                {"id": "chapter-1", "title": "第一章", "start_seconds": 0, "end_seconds": 10},
                {"id": "chapter-2", "title": "第二章", "start_seconds": 10, "end_seconds": 20},
            ],
        })
        self.assertEqual(len(result.chapters), 2)

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

    def test_rejects_reversed_chapter_time_range(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            SummaryPayload.model_validate(
                {
                    "title": "概况",
                    "chapters": [
                        {"id": "chapter-2", "title": "第二章", "start_seconds": 37, "end_seconds": 27},
                    ],
                }
            )

        self.assertIn("end_seconds 必须严格大于 start_seconds", str(raised.exception))

    def test_rejects_chapter_image_outside_its_time_range(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            SummaryPayload.model_validate(
                {
                    "title": "概况",
                    "chapters": [
                        {
                            "id": "chapter-1",
                            "title": "第一章",
                            "start_seconds": 10,
                            "end_seconds": 20,
                            "image_timestamp_seconds": 25,
                        },
                    ],
                }
            )

        self.assertIn("image_timestamp_seconds 必须位于章节时间范围内", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
