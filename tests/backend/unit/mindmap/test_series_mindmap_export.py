from __future__ import annotations
import unittest
from backend.video_summary.infrastructure.mindmap_export import render_mindmap_markdown

class SeriesMindmapExportTests(unittest.TestCase):
    def test_export_series_mindmap_markdown(self):
        node = {"id": "root", "title": "机器学习系列", "summary": "",
            "children": [
                {"id": "t1", "title": "监督学习", "summary": "涵盖回归与分类", "children": []},
                {"id": "t2", "title": "无监督学习", "summary": "", "children": []},
            ]}
        result = render_mindmap_markdown(node)
        self.assertIn("机器学习系列", result)
        self.assertIn("监督学习", result)
        self.assertIn("无监督学习", result)

if __name__ == "__main__":
    unittest.main()
