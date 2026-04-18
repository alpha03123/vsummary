from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.citations import build_citations_from_graph_result


class AgentGraphCitationsTests(unittest.TestCase):
    def test_builds_summary_citation(self) -> None:
        citations = build_citations_from_graph_result(
            {
                "retrieval_results": [
                    {
                        "video_id": "1-6",
                        "title": "JManus",
                        "source_type": "summary",
                        "snippet": "JManus 是 Java 多智能体框架。",
                    }
                ]
            }
        )

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].source_type, "summary")
        self.assertEqual(citations[0].slots[0].target_type, "summary")
        self.assertEqual(citations[0].slots[0].video_id, "1-6")

    def test_builds_summary_citation_from_depth_items_shape(self) -> None:
        citations = build_citations_from_graph_result(
            {
                "retrieval_results": [
                    {
                        "depth": "summary",
                        "query": "框架课有哪些？",
                        "items": [
                            {
                                "video_id": "1-7",
                                "title": "AgentScope",
                                "source_type": "summary",
                                "snippet": "讲 AgentScope 的定位和 ReAct 思维链。",
                            }
                        ],
                    }
                ]
            }
        )

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].source_type, "summary")
        self.assertEqual(citations[0].slots[0].video_id, "1-7")

    def test_builds_transcript_citation_with_video_and_transcript_slots(self) -> None:
        citations = build_citations_from_graph_result(
            {
                "retrieval_results": [
                    {
                        "video_id": "1-5",
                        "title": "安装 Nacos 3",
                        "source_type": "transcript_chunk",
                        "slot_label": "端口说明",
                        "best_match": {
                            "start_seconds": 77.53,
                            "end_seconds": 81.69,
                            "text": "第一个端口是8848",
                        },
                        "matches": [
                            {
                                "start_seconds": 77.53,
                                "end_seconds": 81.69,
                                "text": "第一个端口是8848",
                            },
                            {
                                "start_seconds": 86.51,
                                "end_seconds": 89.49,
                                "text": "那么还有一个端口是9848",
                            },
                        ],
                    }
                ]
            }
        )

        self.assertEqual(len(citations), 1)
        citation = citations[0]
        self.assertEqual(citation.source_type, "transcript")
        self.assertEqual(citation.slots[0].target_type, "video")
        self.assertEqual(citation.slots[1].target_type, "transcript")
        self.assertEqual(citation.slots[1].text, "第一个端口是8848")
        self.assertEqual(len(citation.slots[1].candidates), 2)

    def test_builds_transcript_citation_from_depth_items_shape(self) -> None:
        citations = build_citations_from_graph_result(
            {
                "retrieval_results": [
                    {
                        "depth": "video_graph",
                        "query": "定位端口信息",
                        "items": [
                            {
                                "video_id": "1-5",
                                "title": "安装 Nacos 3",
                                "source_type": "transcript_chunk",
                                "label": "端口说明",
                                "best_match": {
                                    "start_seconds": 77.53,
                                    "end_seconds": 81.69,
                                    "text": "第一个端口是8848",
                                },
                                "matches": [
                                    {
                                        "start_seconds": 77.53,
                                        "end_seconds": 81.69,
                                        "text": "第一个端口是8848",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].source_type, "transcript")
        self.assertEqual(citations[0].slots[1].text, "第一个端口是8848")


if __name__ == "__main__":
    unittest.main()
