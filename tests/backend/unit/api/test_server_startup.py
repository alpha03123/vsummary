from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from backend.api.http.server import configure_event_loop_policy


class ServerStartupTests(unittest.TestCase):
    def test_configures_windows_selector_event_loop_policy_when_available(self) -> None:
        policy = object()
        original_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        asyncio.WindowsSelectorEventLoopPolicy = lambda: policy  # type: ignore[attr-defined]
        try:
            with patch("backend.api.http.server.sys.platform", "win32"), patch(
                "backend.api.http.server.asyncio.set_event_loop_policy"
            ) as set_policy:
                configure_event_loop_policy()

            set_policy.assert_called_once_with(policy)
        finally:
            if original_policy is None:
                delattr(asyncio, "WindowsSelectorEventLoopPolicy")
            else:
                asyncio.WindowsSelectorEventLoopPolicy = original_policy  # type: ignore[attr-defined]

    def test_does_not_change_event_loop_policy_on_non_windows(self) -> None:
        with patch("backend.api.http.server.sys.platform", "linux"), patch(
            "backend.api.http.server.asyncio.set_event_loop_policy"
        ) as set_policy:
            configure_event_loop_policy()

        set_policy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
