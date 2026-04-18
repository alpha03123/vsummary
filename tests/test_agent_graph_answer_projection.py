from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.nodes import _project_answer_evidence


class AgentGraphAnswerProjectionTests(unittest.TestCase):
    def test_project_answer_evidence_keeps_all_video_graph_slots(self) -> None:
        projected = _project_answer_evidence(
            [
                {
                    "depth": "video_graph",
                    "items": [
                        {
                            "video_id": "1-5 准备工作：安装Nacos 3",
                            "title": "1-5 准备工作：安装Nacos 3",
                            "best_match": {
                                "start_seconds": 45.25,
                                "end_seconds": 48.77,
                                "text": "接着Docker镜像拉取之后",
                            },
                            "slots": [
                                {
                                    "label": "安装命令开始时间",
                                    "query": "定位安装命令开始时间",
                                    "best_match": {
                                        "start_seconds": 45.25,
                                        "end_seconds": 48.77,
                                        "text": "接着Docker镜像拉取之后",
                                    },
                                },
                                {
                                    "label": "端口说明",
                                    "query": "定位端口说明",
                                    "best_match": {
                                        "start_seconds": 81.69,
                                        "end_seconds": 84.37,
                                        "text": "也是后面课程中会用到的端口",
                                    },
                                },
                                {
                                    "label": "默认登录信息",
                                    "query": "定位默认登录信息",
                                    "best_match": {
                                        "start_seconds": 113.15,
                                        "end_seconds": 117.05,
                                        "text": "它这里要你输入用户名和密码",
                                    },
                                },
                            ],
                        }
                    ],
                }
            ]
        )

        self.assertEqual(len(projected), 3)
        self.assertEqual(projected[0]["snippet"], "接着Docker镜像拉取之后")
        self.assertEqual(projected[1]["snippet"], "也是后面课程中会用到的端口")
        self.assertEqual(projected[2]["snippet"], "它这里要你输入用户名和密码")


if __name__ == "__main__":
    unittest.main()
