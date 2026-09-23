from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from backend.api.http.server import configure_event_loop_policy
from backend.local.http.server import _exit_for_mysql_path_error


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

    def test_path_error_is_rendered_without_a_traceback(self) -> None:
        with self.assertRaises(SystemExit) as context:
            _exit_for_mysql_path_error(RuntimeError("请将完整安装包移动到纯英文路径后重新启动。"))

        self.assertEqual(str(context.exception), "启动失败：请将完整安装包移动到纯英文路径后重新启动。")


if __name__ == "__main__":
    unittest.main()
