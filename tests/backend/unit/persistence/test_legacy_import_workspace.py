from __future__ import annotations

import unittest
from unittest.mock import Mock

from backend.local.persistence.legacy_workspace_importer import LegacyWorkspaceImporter


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
