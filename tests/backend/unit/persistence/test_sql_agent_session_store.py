from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.persistence.sql_agent_session_store import SqlAgentSessionStore


class _Result:
    def scalar(self):
        return None


class _RecordingSession:
    def __init__(self, calls: list[tuple[str, dict[str, object]]]) -> None:
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, statement, params):
        self._calls.append((str(statement), dict(params)))
        return _Result()


class _RecordingFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self):
        return _RecordingSession(self.calls)

    @property
    def begin(self):
        return self


class SqlAgentSessionStoreTests(unittest.TestCase):
    def test_rejects_missing_workspace_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace_id"):
            SqlAgentSessionStore(_RecordingFactory(), workspace_id="")

    def test_reads_and_clears_only_the_bound_workspace(self) -> None:
        sessions = _RecordingFactory()
        store = SqlAgentSessionStore(sessions, workspace_id="workspace-a")

        self.assertIsNone(store.get_snapshot("shared-session"))
        store.clear_snapshot("shared-session")

        self.assertEqual(
            [params for _statement, params in sessions.calls],
            [
                {"workspace": "workspace-a", "id": "shared-session"},
                {"workspace": "workspace-a", "id": "shared-session"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
