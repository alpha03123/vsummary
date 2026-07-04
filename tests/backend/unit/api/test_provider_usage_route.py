from __future__ import annotations

from datetime import datetime, timezone
import unittest

from backend.api.routes.settings import get_provider_usage
from backend.shared.llm.usage import (
    LlmUsageCategorySummary,
    LlmUsageProviderSummary,
    LlmUsageRecord,
    LlmUsageSummary,
    LlmUsageTimelineBucket,
    LlmUsageTotals,
)


class ProviderUsageRouteTests(unittest.TestCase):
    def test_returns_usage_summary_from_container_store(self) -> None:
        summary = LlmUsageSummary(
            range_key="7d",
            total=LlmUsageTotals(prompt_tokens=100, completion_tokens=40, total_tokens=140),
            by_category=[
                LlmUsageCategorySummary(
                    category="generation",
                    prompt_tokens=80,
                    completion_tokens=30,
                    total_tokens=110,
                )
            ],
            by_provider=[
                LlmUsageProviderSummary(
                    provider="openai",
                    base_url="https://api.example.test/v1",
                    model="openai/gpt-test",
                    prompt_tokens=100,
                    completion_tokens=40,
                    total_tokens=140,
                )
            ],
            recent=[
                LlmUsageRecord(
                    created_at=datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc),
                    category="generation",
                    provider="openai",
                    base_url="https://api.example.test/v1",
                    model="openai/gpt-test",
                    prompt_tokens=100,
                    completion_tokens=40,
                    total_tokens=140,
                )
            ],
            timeline_granularity="day",
            timeline=[
                LlmUsageTimelineBucket(
                    started_at=datetime(2026, 7, 3, 0, 0, tzinfo=timezone.utc),
                    generation_tokens=140,
                    chat_tokens=0,
                    total_tokens=140,
                )
            ],
        )
        container = FakeContainer(summary)

        response = get_provider_usage(container=container, range="7d")

        self.assertEqual(container.usage_store.range_key, "7d")
        self.assertEqual(response.total.total_tokens, 140)
        self.assertEqual(response.by_provider[0].base_url, "https://api.example.test/v1")
        self.assertEqual(response.recent[0].created_at, "2026-07-03T10:00:00+00:00")
        self.assertEqual(response.timeline_granularity, "day")
        self.assertEqual(response.timeline[0].started_at, "2026-07-03T00:00:00+00:00")
        self.assertEqual(response.timeline[0].generation_tokens, 140)


class FakeContainer:
    def __init__(self, summary: LlmUsageSummary) -> None:
        self.usage_store = FakeUsageStore(summary)


class FakeUsageStore:
    def __init__(self, summary: LlmUsageSummary) -> None:
        self._summary = summary
        self.range_key = ""

    def summarize(self, *, range_key: str):
        self.range_key = range_key
        return self._summary


if __name__ == "__main__":
    unittest.main()
