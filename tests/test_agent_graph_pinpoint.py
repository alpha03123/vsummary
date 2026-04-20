from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.evidence.pinpoint import VideoGraphPinpointService
from backend.video_summary.library.views import TranscriptSegmentView, VideoTranscriptView


class _Workspace:
    def get_video_transcript(self, series_id: str, video_id: str):
        del series_id, video_id
        return VideoTranscriptView(
            series_id="agent-frameworks",
            video_id="1-5",
            title="1-5 准备工作：安装Nacos 3",
            duration_seconds=None,
            segments=[
                TranscriptSegmentView(start_seconds=20.05, end_seconds=24.05, text="这里我是以Docker的方式去安装Neckers"),
                TranscriptSegmentView(start_seconds=29.47, end_seconds=33.09, text="那么同学们就自己去安装Docker"),
                TranscriptSegmentView(start_seconds=38.71, end_seconds=40.67, text="运行这条命令"),
                TranscriptSegmentView(start_seconds=45.25, end_seconds=48.77, text="接着Docker镜像拉取之后"),
            ],
        )


class _BiasedSemanticScorer:
    def score(self, *, query: str, texts: list[str]) -> list[float]:
        del query
        scores: list[float] = []
        for text in texts:
            if "自己去安装Docker" in text:
                scores.append(1.0)
            else:
                scores.append(0.0)
        return scores


class AgentGraphPinpointTests(unittest.TestCase):
    def test_locate_prefers_topic_entry_for_start_queries(self) -> None:
        service = VideoGraphPinpointService(workspace=_Workspace(), semantic_scorer=_BiasedSemanticScorer())

        result, tool_results = service.locate(
            series_id="agent-frameworks",
            video_id="1-5",
            query="定位本视频中开始讲 Docker 安装命令的大概时间点",
        )

        self.assertEqual(result["best_match"]["start_seconds"], 20.05)
        self.assertEqual(tool_results[1]["payload"]["seek_seconds"], 20.05)


if __name__ == "__main__":
    unittest.main()
