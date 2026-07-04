from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from backend.shared.llm.usage import LlmUsageRecord, SQLiteLlmUsageStore


class SQLiteLlmUsageStoreTests(unittest.TestCase):
    def test_summarizes_usage_by_time_category_and_provider_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteLlmUsageStore(Path(temp_dir) / "usage.sqlite3")
            now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)

            store.record(
                LlmUsageRecord(
                    created_at=now,
                    category="generation",
                    provider="openai",
                    base_url="https://api.example.test/v1",
                    model="gpt-test",
                    prompt_tokens=100,
                    completion_tokens=40,
                    total_tokens=140,
                )
            )
            store.record(
                LlmUsageRecord(
                    created_at=now - timedelta(days=3),
                    category="chat",
                    provider="openai",
                    base_url="https://api.example.test/v1",
                    model="gpt-test",
                    prompt_tokens=30,
                    completion_tokens=10,
                    total_tokens=40,
                )
            )
            store.record(
                LlmUsageRecord(
                    created_at=now - timedelta(days=40),
                    category="generation",
                    provider="deepseek",
                    base_url="https://api.deepseek.example/v1",
                    model="deepseek-test",
                    prompt_tokens=500,
                    completion_tokens=200,
                    total_tokens=700,
                )
            )

            summary = store.summarize(range_key="7d", now=now)

            self.assertEqual(summary.total.total_tokens, 180)
            self.assertEqual(
                {item.category: item.total_tokens for item in summary.by_category},
                {"generation": 140, "chat": 40},
            )
            self.assertEqual(len(summary.by_provider), 1)
            provider = summary.by_provider[0]
            self.assertEqual(provider.provider, "openai")
            self.assertEqual(provider.base_url, "https://api.example.test/v1")
            self.assertEqual(provider.model, "gpt-test")
            self.assertEqual(provider.total_tokens, 180)
            self.assertEqual([item.total_tokens for item in summary.recent], [140, 40])
            self.assertEqual(summary.timeline_granularity, "day")
            non_empty_buckets = {
                item.started_at.date().isoformat(): (item.generation_tokens, item.chat_tokens, item.total_tokens)
                for item in summary.timeline
                if item.total_tokens
            }
            self.assertEqual(
                non_empty_buckets,
                {
                    "2026-06-30": (0, 40, 40),
                    "2026-07-03": (140, 0, 140),
                },
            )
            self.assertEqual(len(summary.timeline), 7)

    def test_summarizes_30_day_usage_by_week(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteLlmUsageStore(Path(temp_dir) / "usage.sqlite3")
            now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)

            store.record(
                LlmUsageRecord(
                    created_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
                    category="generation",
                    provider="openai",
                    base_url="https://api.example.test/v1",
                    model="gpt-test",
                    prompt_tokens=100,
                    completion_tokens=40,
                    total_tokens=140,
                )
            )
            store.record(
                LlmUsageRecord(
                    created_at=datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc),
                    category="chat",
                    provider="openai",
                    base_url="https://api.example.test/v1",
                    model="gpt-test",
                    prompt_tokens=30,
                    completion_tokens=10,
                    total_tokens=40,
                )
            )

            summary = store.summarize(range_key="30d", now=now)

            self.assertEqual(summary.timeline_granularity, "week")
            non_empty_buckets = {
                item.started_at.date().isoformat(): (item.generation_tokens, item.chat_tokens, item.total_tokens)
                for item in summary.timeline
                if item.total_tokens
            }
            self.assertEqual(non_empty_buckets, {"2026-06-08": (140, 40, 180)})


if __name__ == "__main__":
    unittest.main()
