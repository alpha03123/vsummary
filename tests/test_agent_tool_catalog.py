from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent.schemas.tool_calls import ToolPlane
from backend.agent.tools import (
    ALL_TOOL_DEFINITIONS,
    BUSINESS_READ_TOOL_DEFINITIONS,
    UI_ACTION_TOOL_DEFINITIONS,
    list_tool_definitions_for_plane,
)


class AgentToolCatalogTests(unittest.TestCase):
    def test_tool_planes_partition_full_catalog_without_overlap(self) -> None:
        grouped_names = {
            tool.name
            for tool in BUSINESS_READ_TOOL_DEFINITIONS
        } | {
            tool.name
            for tool in UI_ACTION_TOOL_DEFINITIONS
        }

        self.assertEqual(grouped_names, {tool.name for tool in ALL_TOOL_DEFINITIONS})
        self.assertEqual(len(grouped_names), len(ALL_TOOL_DEFINITIONS))

    def test_ui_action_tools_do_not_mix_business_read_plane(self) -> None:
        ui_action_names = {
            tool.name.value
            for tool in list_tool_definitions_for_plane(ToolPlane.UI_ACTION)
        }
        business_read_names = {
            tool.name.value
            for tool in list_tool_definitions_for_plane(ToolPlane.BUSINESS_READ)
        }

        self.assertFalse(ui_action_names & business_read_names)


if __name__ == "__main__":
    unittest.main()
