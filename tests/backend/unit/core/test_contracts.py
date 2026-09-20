from __future__ import annotations

import unittest

from backend.core.context import WorkspaceContext
from backend.core.quota import LocalUnlimitedQuotaGuard, UsageEstimate
from backend.local.composition import LocalWorkspaceContextProvider


class WorkspaceContextTests(unittest.TestCase):
    def test_requires_all_ownership_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace_id"):
            WorkspaceContext(workspace_id="", actor_id="actor", request_id="request")

    def test_local_context_is_explicit_and_stable(self) -> None:
        context = LocalWorkspaceContextProvider(workspace_id="workspace-1").get_context(request_id="request-1")

        self.assertEqual(context.workspace_id, "workspace-1")
        self.assertEqual(context.actor_id, "local-user")
        self.assertEqual(context.request_id, "request-1")


class LocalQuotaTests(unittest.TestCase):
    def test_local_unlimited_policy_still_requires_idempotency_key(self) -> None:
        context = WorkspaceContext(workspace_id="workspace-1", actor_id="local-user", request_id="request-1")
        quota = LocalUnlimitedQuotaGuard()

        reservation = quota.reserve_job(context, "generate_summary", UsageEstimate(units=1), "key-1")

        self.assertEqual(reservation.id, "local:key-1")
        with self.assertRaisesRegex(ValueError, "idempotency_key"):
            quota.reserve_job(context, "generate_summary", UsageEstimate(), "")
