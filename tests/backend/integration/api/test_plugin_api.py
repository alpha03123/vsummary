from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.video_summary.adapters.progress.in_memory_progress_tracker import InMemoryProgressTracker
from backend.video_summary.adapters.plugin.bilibili.models import (
    BilibiliPluginSummaryResult,
    BilibiliPluginVideoKey,
    BilibiliPluginVideoMeta,
)

_DEFAULT_CACHED_SUMMARY = object()


class PluginApiTests(unittest.TestCase):
    def test_generate_bilibili_summary_returns_lightweight_result(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post(
            "/api/plugin/bilibili/summaries",
            json={"url": "https://www.bilibili.com/video/BV1xx411c7mD?p=2"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_id"], "plugin/bilibili/BV1xx411c7mD/p2")
        self.assertEqual(payload["meta"]["bvid"], "BV1xx411c7mD")
        self.assertEqual(payload["meta"]["page"], 2)
        self.assertEqual(payload["summary"], {"title": "第二讲"})

    def test_get_bilibili_summary_returns_not_found_when_missing(self) -> None:
        container = _build_container(cached_summary=None)
        client = TestClient(create_app(container))

        response = client.get("/api/plugin/bilibili/summaries/BV1xx411c7mD/pages/2")

        self.assertEqual(response.status_code, 404)

    def test_cancel_bilibili_summary_marks_plugin_task_cancelling(self) -> None:
        container = _build_container()
        client = TestClient(create_app(container))

        response = client.post("/api/plugin/bilibili/tasks/BV1xx411c7mD/pages/2/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], "plugin/bilibili/BV1xx411c7mD/p2")
        self.assertEqual(
            container.plugin_progress_tracker.get_snapshot("plugin/bilibili/BV1xx411c7mD/p2").status,
            "cancelling",
        )


def _build_container(cached_summary: BilibiliPluginSummaryResult | None | object = _DEFAULT_CACHED_SUMMARY):
    result = _summary_result()
    resolved_cached_summary = result if cached_summary is _DEFAULT_CACHED_SUMMARY else cached_summary

    async def run(url: str, transcript_enhancement_enabled=None):
        del url, transcript_enhancement_enabled
        return result

    return SimpleNamespace(
        root_dir=None,
        generate_bilibili_plugin_summary=SimpleNamespace(
            run=run,
            get_summary=lambda bvid, page=1: resolved_cached_summary,
        ),
        plugin_progress_tracker=InMemoryProgressTracker(),
    )


def _summary_result() -> BilibiliPluginSummaryResult:
    key = BilibiliPluginVideoKey(bvid="BV1xx411c7mD", page=2)
    return BilibiliPluginSummaryResult(
        key=key,
        meta=BilibiliPluginVideoMeta(
            bvid=key.bvid,
            page=key.page,
            video_id=key.video_id,
            title="第二讲",
            source_url="https://www.bilibili.com/video/BV1xx411c7mD?p=2",
            cover_url="https://example.test/cover.jpg",
            duration_seconds=123,
        ),
        summary={"title": "第二讲"},
    )


if __name__ == "__main__":
    unittest.main()
