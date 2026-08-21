from __future__ import annotations

import unittest

from pydantic import ValidationError

from backend.video_summary.generation import FlatMindmapPayload


class FlatMindmapPayloadTests(unittest.TestCase):
    def test_converts_flat_nodes_to_the_existing_tree_shape(self) -> None:
        payload = FlatMindmapPayload.model_validate(
            {
                "root_id": "root",
                "nodes": [
                    {"id": "root", "parent_id": None, "title": "课程"},
                    {"id": "topic", "parent_id": "root", "title": "主题"},
                    {"id": "detail", "parent_id": "topic", "title": "细节"},
                ],
            }
        )

        tree = payload.to_tree()

        self.assertEqual(tree.id, "root")
        self.assertEqual(tree.children[0].id, "topic")
        self.assertEqual(tree.children[0].children[0].id, "detail")

    def test_rejects_orphan_nodes(self) -> None:
        with self.assertRaisesRegex(ValidationError, "parent_id 不存在"):
            FlatMindmapPayload.model_validate(
                {
                    "root_id": "root",
                    "nodes": [
                        {"id": "root", "parent_id": None, "title": "课程"},
                        {"id": "topic", "parent_id": "missing", "title": "主题"},
                    ],
                }
            )

    def test_rejects_parent_cycles(self) -> None:
        with self.assertRaisesRegex(ValidationError, "不能形成父子环"):
            FlatMindmapPayload.model_validate(
                {
                    "root_id": "root",
                    "nodes": [
                        {"id": "root", "parent_id": None, "title": "课程"},
                        {"id": "first", "parent_id": "second", "title": "一"},
                        {"id": "second", "parent_id": "first", "title": "二"},
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
