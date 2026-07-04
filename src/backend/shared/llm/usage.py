"""LLM API token 用量记录与聚合。

只记录模型供应商真实返回的 usage，不做本地估算，避免把估算值误当成账单。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Protocol
import sqlite3


class LlmUsageCategory(StrEnum):
    GENERATION = "generation"
    CHAT = "chat"


@dataclass(frozen=True)
class LlmUsageRecord:
    created_at: datetime
    category: LlmUsageCategory | str
    provider: str
    base_url: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LlmUsageTotals:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LlmUsageCategorySummary:
    category: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LlmUsageProviderSummary:
    provider: str
    base_url: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LlmUsageTimelineBucket:
    started_at: datetime
    generation_tokens: int
    chat_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LlmUsageSummary:
    range_key: str
    total: LlmUsageTotals
    by_category: list[LlmUsageCategorySummary]
    by_provider: list[LlmUsageProviderSummary]
    recent: list[LlmUsageRecord]
    timeline_granularity: str
    timeline: list[LlmUsageTimelineBucket]


class LlmUsageRecorder(Protocol):
    def record(self, record: LlmUsageRecord) -> None:
        """记录一条 LLM 用量。"""


class SQLiteLlmUsageStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def record(self, record: LlmUsageRecord) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO llm_usage (
                    created_at, category, provider, base_url, model,
                    prompt_tokens, completion_tokens, total_tokens
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _format_datetime(record.created_at),
                    record.category,
                    record.provider,
                    record.base_url,
                    record.model,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def summarize(self, *, range_key: str, now: datetime | None = None) -> LlmUsageSummary:
        resolved_now = now or datetime.now(timezone.utc)
        started_at = _resolve_range_start(range_key, resolved_now)
        where_sql = ""
        params: tuple[str, ...] = ()
        if started_at is not None:
            where_sql = "WHERE created_at >= ?"
            params = (_format_datetime(started_at),)

        connection = self._connect()
        try:
            total = _fetch_totals(
                connection.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(prompt_tokens), 0),
                        COALESCE(SUM(completion_tokens), 0),
                        COALESCE(SUM(total_tokens), 0)
                    FROM llm_usage
                    {where_sql}
                    """,
                    params,
                ).fetchone()
            )
            by_category = [
                LlmUsageCategorySummary(
                    category=row[0],
                    prompt_tokens=row[1],
                    completion_tokens=row[2],
                    total_tokens=row[3],
                )
                for row in connection.execute(
                    f"""
                    SELECT category, SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens)
                    FROM llm_usage
                    {where_sql}
                    GROUP BY category
                    ORDER BY SUM(total_tokens) DESC
                    """,
                    params,
                )
            ]
            by_provider = [
                LlmUsageProviderSummary(
                    provider=row[0],
                    base_url=row[1],
                    model=row[2],
                    prompt_tokens=row[3],
                    completion_tokens=row[4],
                    total_tokens=row[5],
                )
                for row in connection.execute(
                    f"""
                    SELECT provider, base_url, model, SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens)
                    FROM llm_usage
                    {where_sql}
                    GROUP BY provider, base_url, model
                    ORDER BY SUM(total_tokens) DESC
                    """,
                    params,
                )
            ]
            recent = [
                LlmUsageRecord(
                    created_at=_parse_datetime(row[0]),
                    category=row[1],
                    provider=row[2],
                    base_url=row[3],
                    model=row[4],
                    prompt_tokens=row[5],
                    completion_tokens=row[6],
                    total_tokens=row[7],
                )
                for row in connection.execute(
                    f"""
                    SELECT created_at, category, provider, base_url, model,
                           prompt_tokens, completion_tokens, total_tokens
                    FROM llm_usage
                    {where_sql}
                    ORDER BY created_at DESC, id DESC
                    LIMIT 50
                    """,
                    params,
                )
            ]
            timeline_rows = [
                (_parse_datetime(row[0]), row[1], row[2])
                for row in connection.execute(
                    f"""
                    SELECT created_at, category, total_tokens
                    FROM llm_usage
                    {where_sql}
                    ORDER BY created_at ASC, id ASC
                    """,
                    params,
                )
            ]
        finally:
            connection.close()

        timeline_granularity, timeline = _build_timeline(
            timeline_rows,
            range_key=range_key,
            started_at=started_at,
            now=resolved_now,
        )
        return LlmUsageSummary(
            range_key=range_key,
            total=total,
            by_category=by_category,
            by_provider=by_provider,
            recent=recent,
            timeline_granularity=timeline_granularity,
            timeline=timeline,
        )

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at
                ON llm_usage(created_at)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)


def _resolve_range_start(range_key: str, now: datetime) -> datetime | None:
    normalized = range_key.strip().lower()
    if normalized == "today":
        return _floor_day(now)
    if normalized == "7d":
        return _floor_day(now) - timedelta(days=6)
    if normalized == "30d":
        return _floor_day(now) - timedelta(days=29)
    if normalized == "all":
        return None
    raise ValueError(f"unsupported usage range '{range_key}'")


def _build_timeline(
    rows: list[tuple[datetime, str, int]],
    *,
    range_key: str,
    started_at: datetime | None,
    now: datetime,
) -> tuple[str, list[LlmUsageTimelineBucket]]:
    normalized_range = range_key.strip().lower()
    if normalized_range == "today":
        granularity = "hour"
    elif normalized_range == "7d":
        granularity = "day"
    elif normalized_range == "30d":
        granularity = "week"
    else:
        granularity = _choose_all_range_granularity(rows, now)

    if not rows:
        return granularity, []

    start = _resolve_timeline_start(rows[0][0], started_at, granularity)
    end = _resolve_timeline_end(now, granularity)
    buckets: dict[datetime, dict[str, int]] = {}
    cursor = start
    while cursor < end:
        buckets[cursor] = {"generation": 0, "chat": 0}
        cursor = _add_bucket(cursor, granularity)

    for created_at, category, total_tokens in rows:
        bucket_start = _floor_bucket(created_at, granularity)
        if bucket_start not in buckets:
            continue
        if category == LlmUsageCategory.GENERATION:
            buckets[bucket_start]["generation"] += int(total_tokens)
        elif category == LlmUsageCategory.CHAT:
            buckets[bucket_start]["chat"] += int(total_tokens)
        else:
            raise ValueError(f"unsupported usage category '{category}'")

    return granularity, [
        LlmUsageTimelineBucket(
            started_at=bucket_start,
            generation_tokens=values["generation"],
            chat_tokens=values["chat"],
            total_tokens=values["generation"] + values["chat"],
        )
        for bucket_start, values in buckets.items()
    ]


def _choose_all_range_granularity(rows: list[tuple[datetime, str, int]], now: datetime) -> str:
    if not rows:
        return "day"
    span = now - rows[0][0]
    if span.days > 365:
        return "month"
    if span.days > 90:
        return "week"
    return "day"


def _resolve_timeline_start(first_created_at: datetime, started_at: datetime | None, granularity: str) -> datetime:
    return _floor_bucket(started_at or first_created_at, granularity)


def _resolve_timeline_end(now: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return _floor_day(now) + timedelta(days=1)
    return _add_bucket(_floor_bucket(now, granularity), granularity)


def _floor_bucket(value: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return _floor_day(value)
    if granularity == "week":
        return _floor_day(value) - timedelta(days=value.weekday())
    if granularity == "month":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported timeline granularity '{granularity}'")


def _add_bucket(value: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return value + timedelta(hours=1)
    if granularity == "day":
        return value + timedelta(days=1)
    if granularity == "week":
        return value + timedelta(days=7)
    if granularity == "month":
        if value.month == 12:
            return value.replace(year=value.year + 1, month=1)
        return value.replace(month=value.month + 1)
    raise ValueError(f"unsupported timeline granularity '{granularity}'")


def _floor_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _fetch_totals(row) -> LlmUsageTotals:
    return LlmUsageTotals(
        prompt_tokens=int(row[0] or 0),
        completion_tokens=int(row[1] or 0),
        total_tokens=int(row[2] or 0),
    )


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
