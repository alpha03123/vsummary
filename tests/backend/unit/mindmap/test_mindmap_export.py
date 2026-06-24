from __future__ import annotations

import unittest

from backend.video_summary.infrastructure.storage.mindmap_export import render_mindmap_markdown


class MindmapExportTests(unittest.TestCase):
    def test_export_renders_nested_markdown_list(self):
        node = {
            "id": "root",
            "title": "根节点",
            "summary": "",
            "children": [
                {
                    "id": "c1",
                    "title": "子节点1",
                    "summary": "这是摘要",
                    "children": [
                        {"id": "gc1", "title": "孙节点", "summary": "", "children": []},
                    ],
                },
                {"id": "c2", "title": "子节点2", "summary": "", "children": []},
            ],
        }
        result = render_mindmap_markdown(node)
        self.assertIn("- **根节点**", result)
        self.assertIn("  - **子节点1**", result)
        self.assertIn("    这是摘要", result)
        self.assertIn("    - **孙节点**", result)
        self.assertIn("  - **子节点2**", result)

    def test_export_handles_single_root_node(self):
        node = {"id": "root", "title": "唯一节点", "summary": "", "children": []}
        result = render_mindmap_markdown(node)
        self.assertEqual(result, "- **唯一节点**")

    def test_export_handles_empty_children(self):
        node = {"id": "root", "title": "根", "summary": "", "children": []}
        result = render_mindmap_markdown(node)
        self.assertEqual(result, "- **根**")

    def test_export_includes_node_summary(self):
        node = {
            "id": "root",
            "title": "根",
            "summary": "重要摘要内容",
            "children": [],
        }
        result = render_mindmap_markdown(node)
        self.assertIn("重要摘要内容", result)


class MindmapHtmlExportTests(unittest.TestCase):
    def test_html_export_renders_valid_html(self):
        from backend.video_summary.infrastructure.storage.mindmap_export import render_mindmap_html
        node = {"id": "root", "title": "TestTitle", "summary": "", "children": []}
        result = render_mindmap_html(node, "TestTitle")
        self.assertTrue(result.startswith("<!doctype html>"))
        self.assertIn("markmap-view", result)
        self.assertIn("TestTitle", result)

    def test_html_export_embeds_mindmap_data(self):
        from backend.video_summary.infrastructure.storage.mindmap_export import render_mindmap_html
        node = {"id": "root", "title": "Root Node", "summary": "A summary", "children": []}
        result = render_mindmap_html(node, "Root Node")
        self.assertIn('Root Node', result)
        self.assertIn('A summary', result)

    def test_html_export_handles_nested_children(self):
        from backend.video_summary.infrastructure.storage.mindmap_export import render_mindmap_html
        node = {"id": "root", "title": "Root", "summary": "", "children": [
            {"id": "c1", "title": "Child1", "summary": "", "children": []}
        ]}
        result = render_mindmap_html(node, "Root")
        self.assertIn('Child1', result)


if __name__ == "__main__":
    unittest.main()
