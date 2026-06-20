from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from backend.video_summary.library.models import LibraryVideoCardDTO


class LibraryVideoCardDTOTest(unittest.TestCase):
    def test_default_core_problem_is_empty_string(self) -> None:
        card = LibraryVideoCardDTO(
            id="v1", title="V1", source_name="v1.mp4",
            processed=False, status="pending",
        )
        self.assertEqual(card.core_problem, "")

    def test_explicit_core_problem_is_preserved(self) -> None:
        card = LibraryVideoCardDTO(
            id="v1", title="V1", source_name="v1.mp4",
            processed=True, status="ready",
            core_problem="如何用三步拆解复杂问题",
        )
        self.assertEqual(card.core_problem, "如何用三步拆解复杂问题")

    def test_dto_remains_frozen_after_field_added(self) -> None:
        card = LibraryVideoCardDTO(
            id="v1", title="V1", source_name="v1.mp4",
            processed=False, status="pending",
        )
        with self.assertRaises(FrozenInstanceError):
            card.core_problem = "不应该能改"  # type: ignore[misc]
