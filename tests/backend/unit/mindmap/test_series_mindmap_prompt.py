from __future__ import annotations
import unittest


class SeriesMindmapPromptTests(unittest.TestCase):
    def _build_prompt(self, series_title="测试系列", catalog=None, video_summaries=None):
        from backend.video_summary.infrastructure.litellm_series_mindmap_generator import build_series_mindmap_prompt
        return build_series_mindmap_prompt(
            series_title=series_title,
            catalog=catalog or {"series_title": "测试系列", "videos": []},
            video_summaries=video_summaries or [],
        )

    def test_prompt_includes_series_title(self):
        prompt = self._build_prompt(series_title="机器学习课程")
        self.assertIn("机器学习课程", prompt)

    def test_prompt_includes_video_summaries(self):
        summaries = [{"title": "第一课", "one_sentence_summary": "介绍基础概念"}]
        prompt = self._build_prompt(video_summaries=summaries)
        self.assertIn("第一课", prompt)
        self.assertIn("介绍基础概念", prompt)

    def test_prompt_truncates_large_summaries(self):
        summaries = [
            {"title": f"视频{i}", "one_sentence_summary": f"概要{i}", "chapters": [{"title": "长章节" * 500}]}
            for i in range(50)
        ]
        prompt = self._build_prompt(video_summaries=summaries)
        for i in range(50):
            self.assertIn(f"视频{i}", prompt)
        self.assertNotIn("长章节" * 500, prompt)

    def test_prompt_falls_back_without_catalog(self):
        prompt = self._build_prompt(catalog=None, video_summaries=[{"title": "T1"}])
        self.assertIn("T1", prompt)


if __name__ == "__main__":
    unittest.main()
