from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from backend.local.persistence.legacy_workspace_importer import (
    LegacyWorkspaceImporter,
    _legacy_knowledge_card_rows,
    _latest_agent_note_as_ai_summary,
    _legacy_transcript_payload,
)


class _Rows:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def scalars(self):
        return self

    def all(self) -> list[str]:
        return self._values


class _Session:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, *_args):
        return _Rows(self._values)


class _Sessions:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def __call__(self):
        return _Session(self._values)


class LegacyImportWorkspaceTests(unittest.TestCase):
    def test_reuses_the_existing_local_installation_workspace(self) -> None:
        importer = LegacyWorkspaceImporter(root_dir=Mock(), session_factory=_Sessions(["local-workspace"]), blob_store=Mock())
        importer._mapped = Mock(return_value=None)
        importer._record = Mock()
        importer._control = Mock()

        workspace_id = importer._workspace_id()

        self.assertEqual(workspace_id, "local-workspace")
        importer._control.create_workspace.assert_not_called()

    def test_refuses_to_guess_when_multiple_local_workspaces_exist(self) -> None:
        importer = LegacyWorkspaceImporter(root_dir=Mock(), session_factory=_Sessions(["first", "second"]), blob_store=Mock())
        importer._mapped = Mock(return_value=None)
        importer._control = Mock()

        with self.assertRaisesRegex(RuntimeError, "Multiple local-installation"):
            importer._workspace_id()


class LegacyPayloadConversionTests(unittest.TestCase):
    def test_preserves_a_transcript_without_a_summary(self) -> None:
        transcript = _legacy_transcript_payload(
            {
                "language": "zh",
                "duration_seconds": 2.5,
                "segments": [{"start_seconds": 0.0, "end_seconds": 2.5, "text": "独立转写"}],
            }
        )

        self.assertEqual(transcript["language"], "zh")
        self.assertEqual(transcript["duration_ms"], 2500)
        self.assertEqual(transcript["segments"], [{"start": 0, "end": 2500, "text": "独立转写"}])

    def test_promotes_latest_legacy_agent_note_only(self) -> None:
        summary = _latest_agent_note_as_ai_summary(
            {
                "notes": [
                    {"source": "manual", "title": "手写", "content": "保留为笔记", "updated_at": "2026-01-02"},
                    {"source": "agent", "title": "旧概括", "content": "旧内容", "updated_at": "2026-01-01"},
                    {"source": "agent", "title": "新概括", "content": "新内容", "updated_at": "2026-01-03"},
                ]
            }
        )

        self.assertEqual(summary, {"title": "新概括", "content": "新内容", "citations": "[]"})

    def test_knowledge_cards_receive_global_ids_and_rewrite_local_relationships(self) -> None:
        title, rows = _legacy_knowledge_card_rows(
            {
                "title": "旧版卡片",
                "cards": [
                    {"id": "kc-1", "title": "第一张", "related_card_ids": ["kc-2", "missing"]},
                    {"id": "kc-2", "title": "第二张", "related_card_ids": ["kc-1"]},
                ],
            }
        )

        self.assertEqual(title, "旧版卡片")
        self.assertTrue(all(len(row["id"]) == 26 for row in rows))
        self.assertNotIn("kc-1", {row["id"] for row in rows})
        self.assertEqual(json.loads(rows[0]["related"]), [rows[1]["id"]])
        self.assertEqual(json.loads(rows[1]["related"]), [rows[0]["id"]])

    def test_knowledge_cards_from_different_videos_do_not_reuse_legacy_ids(self) -> None:
        payload = {"cards": [{"id": "kc-1", "title": "同名旧卡片"}]}

        _, first_rows = _legacy_knowledge_card_rows(payload)
        _, second_rows = _legacy_knowledge_card_rows(payload)

        self.assertNotEqual(first_rows[0]["id"], second_rows[0]["id"])

    def test_knowledge_cards_without_legacy_ids_receive_global_ids(self) -> None:
        _, rows = _legacy_knowledge_card_rows({"cards": [{"title": "无旧 ID"}]})

        self.assertEqual(len(rows[0]["id"]), 26)
        self.assertEqual(json.loads(rows[0]["related"]), [])

    def test_rejects_ambiguous_duplicate_legacy_knowledge_card_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be unique"):
            _legacy_knowledge_card_rows({"cards": [{"id": "kc-1"}, {"id": "kc-1"}]})
