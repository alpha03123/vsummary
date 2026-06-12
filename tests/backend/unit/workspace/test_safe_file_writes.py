from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


from backend.common.filesystem import atomic_write_text


class SafeFileWriteTests(unittest.TestCase):
    def test_atomic_write_text_replaces_existing_file_without_leaving_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "data" / "payload.json"
            target.parent.mkdir(parents=True)
            target.write_text("old", encoding="utf-8")

            atomic_write_text(target, "new")

            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertEqual([path.name for path in target.parent.iterdir()], ["payload.json"])


if __name__ == "__main__":
    unittest.main()
