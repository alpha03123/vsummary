from __future__ import annotations

import unittest

from backend.video_summary.library.linked_models import LinkedSeries, LinkedVideo
from backend.video_summary.library.usecases.linked_videos import CreateAgentLinkedSeries


class CreateAgentLinkedSeriesTests(unittest.TestCase):
    def test_creates_empty_linked_series_with_stable_agent_id(self) -> None:
        workspace = _FakeLinkedSeriesWorkspace()
        invalidator = _FakeWorkspaceIndexInvalidator()
        usecase = CreateAgentLinkedSeries(workspace, invalidator)

        series = usecase.run(title="  Transformer 入门  ")

        self.assertEqual(series.id, "agent-transformer")
        self.assertEqual(series.title, "Transformer 入门")
        self.assertEqual(series.videos, [])
        self.assertTrue(series.is_linked)
        self.assertTrue(series.is_agent_managed)
        self.assertEqual(series.source_url, "")
        self.assertEqual(workspace.saved_ids, ["agent-transformer"])
        self.assertEqual(invalidator.invalidate_count, 1)

    def test_reuses_existing_series_with_same_title_without_overwriting_videos(self) -> None:
        workspace = _FakeLinkedSeriesWorkspace()
        invalidator = _FakeWorkspaceIndexInvalidator()
        workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-transformer",
                title="Transformer 入门",
                cover_url="cover.jpg",
                source_url="",
                is_agent_managed=True,
                videos=[
                    LinkedVideo(
                        bvid="BVexisting",
                        page=1,
                        title="Existing",
                        cover_url="",
                        duration_seconds=0,
                        source_url="https://www.bilibili.com/video/BVexisting",
                    )
                ],
            )
        )
        usecase = CreateAgentLinkedSeries(workspace, invalidator)

        series = usecase.run(title="Transformer 入门")

        self.assertEqual(series.id, "agent-transformer")
        self.assertEqual(len(series.videos), 1)
        self.assertEqual(workspace.saved_ids, ["agent-transformer"])
        self.assertEqual(invalidator.invalidate_count, 0)

    def test_uses_unique_id_when_slug_collides_with_different_title(self) -> None:
        workspace = _FakeLinkedSeriesWorkspace()
        invalidator = _FakeWorkspaceIndexInvalidator()
        workspace.save_linked_series(
            LinkedSeries(
                series_id="agent-transformer",
                title="Existing Transformer",
                cover_url="",
                source_url="",
                is_agent_managed=True,
                videos=[],
            )
        )
        usecase = CreateAgentLinkedSeries(workspace, invalidator)

        series = usecase.run(title="Transformer 入门")

        self.assertTrue(series.id.startswith("agent-transformer-"))
        self.assertNotEqual(series.id, "agent-transformer")
        self.assertEqual(series.title, "Transformer 入门")
        self.assertEqual(invalidator.invalidate_count, 1)


class _FakeLinkedSeriesWorkspace:
    def __init__(self) -> None:
        self.series: dict[str, LinkedSeries] = {}
        self.saved_ids: list[str] = []

    def save_linked_series(self, series: LinkedSeries) -> None:
        self.series[series.series_id] = series
        self.saved_ids.append(series.series_id)

    def get_linked_series(self, series_id: str) -> LinkedSeries | None:
        return self.series.get(series_id)


class _FakeWorkspaceIndexInvalidator:
    def __init__(self) -> None:
        self.invalidate_count = 0

    def invalidate(self) -> None:
        self.invalidate_count += 1


if __name__ == "__main__":
    unittest.main()
