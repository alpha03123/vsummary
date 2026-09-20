from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace


class SqlVideoWorkspaceBoundaryTests(unittest.TestCase):
    def test_requires_an_explicit_workspace_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace_id"):
            SqlVideoWorkspace(
                session_factory=Mock(),
                blob_store=Mock(),
                cache_root=Path("cache"),
                workspace_id="",
            )

    def test_binds_the_composition_workspace_id(self) -> None:
        workspace = SqlVideoWorkspace(
            session_factory=Mock(),
            blob_store=Mock(),
            cache_root=Path("cache"),
            workspace_id="workspace-1",
        )

        self.assertEqual(workspace.workspace_id, "workspace-1")
