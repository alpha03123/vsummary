from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.video_summary.infrastructure.storage.filesystem_video_workspace import (
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


class ListSeriesCoreProblemTests(unittest.TestCase):
    """list_series 端到端返回 DTO 时填入 core_problem 字段。"""

    def _seed_workspace(self, root: Path, series_id: str, video_id: str, *, with_summary: bool, core_problem: str = "") -> None:
        """seed 一个最小本地 series + video,可选地写 summary.json。"""
        (root / "videos" / series_id).mkdir(parents=True)
        (root / "videos" / series_id / f"{video_id}.mp4").write_bytes(b"\x00")
        if with_summary:
            summary_dir = root / "workspace" / series_id / video_id
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text(
                json.dumps({"core_problem": core_problem}), encoding="utf-8"
            )

    def test_pure_local_video_includes_core_problem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_workspace(root, "s1", "v1", with_summary=True, core_problem="如何 X")
            ws = FileSystemVideoWorkspace(root)
            series_list = ws.list_series()
            cards = [c for s in series_list for c in s.videos if c.id == "v1"]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].core_problem, "如何 X")

    def test_pure_local_video_omits_core_problem_when_no_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_workspace(root, "s1", "v1", with_summary=False)
            ws = FileSystemVideoWorkspace(root)
            series_list = ws.list_series()
            cards = [c for s in series_list for c in s.videos if c.id == "v1"]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].core_problem, "")

    def test_linked_without_local_file_has_empty_core_problem(self) -> None:
        """linked 系列,本地无视频文件,core_problem 必为空。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace" / "s_linked").mkdir(parents=True)
            (root / "workspace" / "s_linked" / "linked_series.json").write_text(
                json.dumps({
                    "title": "Linked Series",
                    "source_url": "https://example.com",
                    "videos": [
                        {"bvid": "BV_LINKED", "page": 1, "title": "Linked V1",
                         "source_url": "https://example.com/v1", "provider": "bilibili"}
                    ],
                }),
                encoding="utf-8",
            )
            ws = FileSystemVideoWorkspace(root)
            series_list = ws.list_series()
            cards = [c for s in series_list for c in s.videos if c.id == "BV_LINKED"]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].core_problem, "")
            self.assertTrue(cards[0].is_linked)

    def test_linked_with_local_file_pulls_core_problem_from_local_summary(self) -> None:
        """linked 系列,本地已下载且有 summary.json,应能拿到 core_problem。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace" / "s_linked").mkdir(parents=True)
            (root / "workspace" / "s_linked" / "linked_series.json").write_text(
                json.dumps({
                    "title": "Linked Series",
                    "source_url": "https://example.com",
                    "videos": [
                        {"bvid": "BV_DOWNLOADED", "page": 1, "title": "Downloaded V",
                         "source_url": "https://example.com/v", "provider": "bilibili"}
                    ],
                }),
                encoding="utf-8",
            )
            # 本地视频文件存在
            (root / "videos" / "s_linked").mkdir(parents=True)
            (root / "videos" / "s_linked" / "BV_DOWNLOADED.mp4").write_bytes(b"\x00")
            # 本地 summary.json 存在
            summary_dir = root / "workspace" / "s_linked" / "BV_DOWNLOADED"
            summary_dir.mkdir(parents=True)
            (summary_dir / "summary.json").write_text(
                json.dumps({"core_problem": "已下载并已总结"}), encoding="utf-8"
            )
            ws = FileSystemVideoWorkspace(root)
            series_list = ws.list_series()
            cards = [c for s in series_list for c in s.videos if c.id == "BV_DOWNLOADED"]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].core_problem, "已下载并已总结")
            self.assertFalse(cards[0].is_linked)
