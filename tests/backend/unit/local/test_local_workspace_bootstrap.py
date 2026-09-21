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

    def scalar_one(self):
        return self._scalar

    def scalars(self) -> _Scalars:
        return _Scalars(self._values)


class _Session:
    def __init__(
        self,
        *,
        has_workspaces: bool,
        local_workspace_ids: list[str] | None = None,
        legacy_workspace_ids: list[str] | None = None,
        series_counts: dict[str, int] | None = None,
        active_job_counts: dict[str, int] | None = None,
    ) -> None:
        self._has_workspaces = has_workspaces
        self._local_workspace_ids = local_workspace_ids or []
        self._legacy_workspace_ids = legacy_workspace_ids or []
        self._series_counts = series_counts or {}
        self._active_job_counts = active_job_counts or {}
        self.inserts: list[dict[str, str]] = []
        self.promoted_workspace_ids: list[str] = []
        self.deleted_workspace_ids: list[str] = []

    def execute(self, statement, params=None):
        rendered = str(statement)
        if "SHOW TABLES" in rendered:
            return _Result(scalar="workspaces" if self._has_workspaces else None)
        if rendered.startswith("UPDATE workspaces SET deleted_at"):
            self.deleted_workspace_ids.append(params["workspace"])
            return _Result()
        if rendered.startswith("UPDATE workspaces SET owner_scope_id"):
            self.promoted_workspace_ids.append(params["workspace"])
            return _Result()
        if "owner_scope_id='local-installation'" in rendered:
            return _Result(values=self._local_workspace_ids)
        if "owner_scope_id='legacy-local'" in rendered:
            return _Result(values=self._legacy_workspace_ids)
        if rendered.startswith("SELECT COUNT(*) FROM series"):
            return _Result(scalar=self._series_counts[params["workspace"]])
        if rendered.startswith("SELECT COUNT(*) FROM jobs"):
            return _Result(scalar=self._active_job_counts.get(params["workspace"], 0))
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
        session = _Session(has_workspaces=False)

        self.assertIsNone(ensure_local_workspace_before_migration(_Factory(session)))
        self.assertEqual(session.inserts, [])

    def test_database_without_any_local_workspace_gets_one_before_migration(self) -> None:
        session = _Session(has_workspaces=True)

        workspace_id = ensure_local_workspace_before_migration(_Factory(session))

        self.assertIsNotNone(workspace_id)
        self.assertEqual(session.inserts, [{"id": workspace_id}])

    def test_legacy_workspace_is_promoted_when_no_current_workspace_exists(self) -> None:
        session = _Session(has_workspaces=True, legacy_workspace_ids=["legacy-workspace"])

        self.assertEqual(ensure_local_workspace_before_migration(_Factory(session)), "legacy-workspace")
        self.assertEqual(session.promoted_workspace_ids, ["legacy-workspace"])
        self.assertEqual(session.inserts, [])

    def test_contentful_legacy_workspace_replaces_empty_bootstrap_workspace(self) -> None:
        session = _Session(
            has_workspaces=True,
            local_workspace_ids=["empty-workspace"],
            legacy_workspace_ids=["legacy-workspace"],
            series_counts={"empty-workspace": 0, "legacy-workspace": 3},
        )

        self.assertEqual(ensure_local_workspace_before_migration(_Factory(session)), "legacy-workspace")
        self.assertEqual(session.deleted_workspace_ids, ["empty-workspace"])
        self.assertEqual(session.promoted_workspace_ids, ["legacy-workspace"])

    def test_refuses_to_choose_between_two_contentful_workspaces(self) -> None:
        session = _Session(
            has_workspaces=True,
            local_workspace_ids=["current-workspace"],
            legacy_workspace_ids=["legacy-workspace"],
            series_counts={"current-workspace": 1, "legacy-workspace": 1},
        )

        with self.assertRaisesRegex(RuntimeError, "Both local-installation"):
            ensure_local_workspace_before_migration(_Factory(session))

    def test_refuses_to_replace_empty_workspace_with_active_jobs(self) -> None:
        session = _Session(
            has_workspaces=True,
            local_workspace_ids=["current-workspace"],
            legacy_workspace_ids=["legacy-workspace"],
            series_counts={"current-workspace": 0, "legacy-workspace": 1},
            active_job_counts={"current-workspace": 1},
        )

        with self.assertRaisesRegex(RuntimeError, "active Jobs"):
            ensure_local_workspace_before_migration(_Factory(session))

    def test_multiple_local_workspaces_are_rejected(self) -> None:
        session = _Session(has_workspaces=True, local_workspace_ids=["workspace-1", "workspace-2"])

        with self.assertRaisesRegex(RuntimeError, "Multiple local-installation"):
            ensure_local_workspace_before_migration(_Factory(session))
