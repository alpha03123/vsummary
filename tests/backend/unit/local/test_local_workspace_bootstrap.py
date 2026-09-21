from __future__ import annotations

import unittest

from backend.local.persistence.local_workspace_bootstrap import ensure_local_workspace_before_migration


class _Scalars:
    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return self._values


class _Result:
    def __init__(self, *, scalar=None, values: list[str] | None = None) -> None:
        self._scalar = scalar
        self._values = values or []

    def scalar(self):
        return self._scalar

    def scalars(self) -> _Scalars:
        return _Scalars(self._values)


class _Session:
    def __init__(self, *, has_workspaces: bool, workspace_ids: list[str]) -> None:
        self._has_workspaces = has_workspaces
        self._workspace_ids = workspace_ids
        self.inserts: list[dict[str, str]] = []

    def execute(self, statement, params=None):
        rendered = str(statement)
        if "SHOW TABLES" in rendered:
            return _Result(scalar="workspaces" if self._has_workspaces else None)
        if rendered.startswith("SELECT id FROM workspaces"):
            return _Result(values=self._workspace_ids)
        if rendered.startswith("INSERT INTO workspaces"):
            self.inserts.append(params)
            return _Result()
        raise AssertionError(rendered)


class _Factory:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def begin(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, *_args):
        return False


class LocalWorkspaceBootstrapTests(unittest.TestCase):
    def test_empty_database_is_left_for_alembic_initialization(self) -> None:
        session = _Session(has_workspaces=False, workspace_ids=[])

        self.assertIsNone(ensure_local_workspace_before_migration(_Factory(session)))
        self.assertEqual(session.inserts, [])

    def test_legacy_database_without_local_workspace_gets_one_before_migration(self) -> None:
        session = _Session(has_workspaces=True, workspace_ids=[])

        workspace_id = ensure_local_workspace_before_migration(_Factory(session))

        self.assertIsNotNone(workspace_id)
        self.assertEqual(session.inserts, [{"id": workspace_id}])

    def test_existing_local_workspace_is_reused(self) -> None:
        session = _Session(has_workspaces=True, workspace_ids=["workspace-1"])

        self.assertEqual(ensure_local_workspace_before_migration(_Factory(session)), "workspace-1")
        self.assertEqual(session.inserts, [])

    def test_multiple_local_workspaces_are_rejected(self) -> None:
        session = _Session(has_workspaces=True, workspace_ids=["workspace-1", "workspace-2"])

        with self.assertRaisesRegex(RuntimeError, "Multiple local-installation"):
            ensure_local_workspace_before_migration(_Factory(session))
