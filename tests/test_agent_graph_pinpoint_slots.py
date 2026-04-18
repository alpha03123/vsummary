from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.pinpoint import _build_probe_slots, extract_query_terms


class AgentGraphPinpointSlotTests(unittest.TestCase):
    def test_extract_query_terms_splits_chinese_query_into_meaningful_terms(self) -> None:
        terms = extract_query_terms("后续讲解端口说明、控制台访问地址")

        self.assertIn("端口", terms)
        self.assertIn("控制台", terms)
        self.assertIn("访问", terms)

    def test_extract_query_terms_keeps_login_credentials_terms(self) -> None:
        terms = extract_query_terms("默认登录用户名密码的大概时间段。输出尽量给出按内容分段的时间范围")

        self.assertIn("登录", terms)
        self.assertIn("用户名", terms)
        self.assertIn("密码", terms)

    def test_build_probe_slots_splits_parallel_locate_clauses(self) -> None:
        slots = _build_probe_slots("再定位讲解端口（如 8848、9848、8080）和控制台默认登录信息（用户名/密码 nacos）的时间段")

        self.assertEqual(len(slots), 2)
        self.assertIn("端口", slots[0]["query"])
        self.assertIn("默认登录信息", slots[1]["query"])

    def test_build_probe_slots_splits_top_level_enumeration_clause(self) -> None:
        slots = _build_probe_slots("后续讲解端口说明、控制台访问地址")

        self.assertEqual(len(slots), 2)
        self.assertIn("端口说明", slots[0]["query"])
        self.assertIn("控制台访问地址", slots[1]["query"])

    def test_build_probe_slots_does_not_split_inner_phrase(self) -> None:
        slots = _build_probe_slots("讲默认控制台登录信息（用户名和密码均为 nacos）的时间段")

        self.assertEqual(len(slots), 1)
        self.assertIn("用户名和密码", slots[0]["query"])


if __name__ == "__main__":
    unittest.main()
