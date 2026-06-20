from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.video_summary.infrastructure.filesystem_video_workspace import (
    FileSystemVideoWorkspace,
)


def _make_workspace(root: Path) -> FileSystemVideoWorkspace:
    """构造最小 workspace 目录: <root>/workspace 与 <root>/videos。"""
    (root / "workspace").mkdir()
    (root / "videos").mkdir()
    return FileSystemVideoWorkspace(root)


class ReadCoreProblemTests(unittest.TestCase):
    """_read_core_problem 4 种降级路径 + 正常路径(B2 验收)。"""

    def test_returns_empty_when_summary_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_workspace(Path(tmp))
            self.assertEqual(ws._read_core_problem("s1", "v1"), "")

    def test_returns_empty_when_summary_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_workspace(Path(tmp))
            summary_dir = ws._workspace_dir / "s1" / "v1"
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text("{ this is not json", encoding="utf-8")
            self.assertEqual(ws._read_core_problem("s1", "v1"), "")

    def test_returns_empty_when_core_problem_not_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_workspace(Path(tmp))
            summary_dir = ws._workspace_dir / "s1" / "v1"
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text(
                json.dumps({"core_problem": 42}), encoding="utf-8"
            )
            self.assertEqual(ws._read_core_problem("s1", "v1"), "")

    def test_returns_empty_when_core_problem_field_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_workspace(Path(tmp))
            summary_dir = ws._workspace_dir / "s1" / "v1"
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text(
                json.dumps({"title": "other"}), encoding="utf-8"
            )
            self.assertEqual(ws._read_core_problem("s1", "v1"), "")

    def test_returns_stripped_string_when_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_workspace(Path(tmp))
            summary_dir = ws._workspace_dir / "s1" / "v1"
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text(
                json.dumps({"core_problem": "  如何拆解复杂问题  \n"}),
                encoding="utf-8",
            )
            self.assertEqual(ws._read_core_problem("s1", "v1"), "如何拆解复杂问题")
