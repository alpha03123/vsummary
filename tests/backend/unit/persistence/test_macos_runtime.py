from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from backend.video_summary.infrastructure.persistence import local_credentials as credentials
from backend.video_summary.infrastructure.persistence import managed_local_mysql as mysql


class PlatformRuntimeTests(unittest.TestCase):
    def test_macos_shutdown_reaps_its_child_instead_of_polling_a_zombie(self):
        runtime = mysql.ManagedLocalMySql(mysql_home=Path("runtime"), data_root=Path("data"))
        runtime._process = Mock(pid=123)
        with patch.object(sys, "platform", "darwin"), patch.object(mysql, "_process_is_running") as probe:
            runtime._wait_for_server_exit(123)
        runtime._process.wait.assert_called_once_with(timeout=15.0)
        probe.assert_not_called()

    def test_macos_data_root_does_not_need_localappdata(self):
        with patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(mysql._default_data_root(), Path.home() / "Library/Application Support/VSummary")

    def test_windows_binary_names_are_preserved(self):
        runtime = mysql.ManagedLocalMySql(mysql_home=Path("runtime"), data_root=Path("data"))
        with patch.object(sys, "platform", "win32"):
            self.assertEqual(runtime._mysqld_path(), Path("runtime/bin/mysqld.exe"))
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(runtime._mysqld_path(), Path("runtime/bin/mysqld"))

    @unittest.skipIf(sys.platform == "win32", "POSIX file lock")
    def test_second_instance_cannot_lock_the_same_data_directory(self):
        with TemporaryDirectory() as directory:
            first = mysql.ManagedLocalMySql(mysql_home=Path(directory), data_root=Path(directory) / "data")
            second = mysql.ManagedLocalMySql(mysql_home=Path(directory), data_root=first.paths.root)
            first._ensure_directories()
            first._acquire_instance_lock()
            try:
                with self.assertRaisesRegex(mysql.ManagedLocalMySqlError, "Another VSummary"):
                    second._acquire_instance_lock()
            finally:
                first._release_instance_lock()
            second._acquire_instance_lock()
            second._release_instance_lock()

    def test_keychain_reference_file_does_not_contain_the_password(self):
        with TemporaryDirectory() as directory, patch.object(sys, "platform", "darwin"):
            path = Path(directory) / "credentials.keychain"
            with patch.object(credentials, "_keychain_password", return_value="private-password") as keychain:
                credentials.save_local_mysql_password(path, "private-password")
                self.assertNotIn("private-password", path.read_text())
                self.assertEqual(credentials.load_local_mysql_password(path), "private-password")
                self.assertEqual(keychain.call_count, 2)

    def test_keychain_failure_does_not_leave_a_success_reference(self):
        with TemporaryDirectory() as directory, patch.object(sys, "platform", "darwin"):
            path = Path(directory) / "credentials.keychain"
            with patch.object(credentials, "_keychain_password", side_effect=credentials.LocalCredentialError("locked")):
                with self.assertRaises(credentials.LocalCredentialError):
                    credentials.save_local_mysql_password(path, "password")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
