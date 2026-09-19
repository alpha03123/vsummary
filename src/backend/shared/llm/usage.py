"""MySQL LLM 用量账本与聚合 DTO。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


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
    def record(self, record: LlmUsageRecord) -> None: ...


class MySqlLlmUsageStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def record(self, record: LlmUsageRecord) -> None:
        from backend.video_summary.infrastructure.persistence.ids import new_ulid
        with self._sessions.begin() as session:
            session.execute(text("INSERT INTO llm_usage (id,created_at,category,provider,base_url,model,prompt_tokens,completion_tokens,total_tokens) VALUES (:id,:created,:category,:provider,:base,:model,:prompt,:completion,:total)"), {"id": new_ulid(), "created": record.created_at, "category": str(record.category), "provider": record.provider, "base": record.base_url, "model": record.model, "prompt": record.prompt_tokens, "completion": record.completion_tokens, "total": record.total_tokens})

    def summarize(self, *, range_key: str, now: datetime | None = None) -> LlmUsageSummary:
        resolved_now = now or datetime.now(timezone.utc)
        started_at = _resolve_range_start(range_key, resolved_now)
        clause = "" if started_at is None else "WHERE created_at >= :started"
        params = {} if started_at is None else {"started": started_at}
        with self._sessions() as session:
            total = session.execute(text(f"SELECT COALESCE(SUM(prompt_tokens),0),COALESCE(SUM(completion_tokens),0),COALESCE(SUM(total_tokens),0) FROM llm_usage {clause}"), params).one()
            categories = session.execute(text(f"SELECT category,SUM(prompt_tokens),SUM(completion_tokens),SUM(total_tokens) FROM llm_usage {clause} GROUP BY category ORDER BY SUM(total_tokens) DESC"), params).all()
            providers = session.execute(text(f"SELECT provider,base_url,model,SUM(prompt_tokens),SUM(completion_tokens),SUM(total_tokens) FROM llm_usage {clause} GROUP BY provider,base_url,model ORDER BY SUM(total_tokens) DESC"), params).all()
            recent = session.execute(text(f"SELECT created_at,category,provider,base_url,model,prompt_tokens,completion_tokens,total_tokens FROM llm_usage {clause} ORDER BY created_at DESC,id DESC LIMIT 50"), params).all()
            rows = session.execute(text(f"SELECT created_at,category,total_tokens FROM llm_usage {clause} ORDER BY created_at,id"), params).all()
        granularity, timeline = _build_timeline(list(rows), range_key=range_key, started_at=started_at, now=resolved_now)
        return LlmUsageSummary(range_key, LlmUsageTotals(*total), [LlmUsageCategorySummary(*row) for row in categories], [LlmUsageProviderSummary(*row) for row in providers], [LlmUsageRecord(*row) for row in recent], granularity, timeline)


def _resolve_range_start(range_key: str, now: datetime) -> datetime | None:
    key = range_key.strip().lower()
    day = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if key == "today": return day
    if key == "7d": return day - timedelta(days=6)
    if key == "30d": return day - timedelta(days=29)
    if key == "all": return None
    raise ValueError(f"unsupported usage range '{range_key}'")


def _build_timeline(rows, *, range_key: str, started_at: datetime | None, now: datetime) -> tuple[str, list[LlmUsageTimelineBucket]]:
    del range_key, started_at, now
    buckets: dict[datetime, dict[str, int]] = defaultdict(lambda: {"generation": 0, "chat": 0})
    for created_at, category, total in rows:
        timestamp = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        bucket = timestamp.replace(minute=0, second=0, microsecond=0)
        buckets[bucket][str(category)] = buckets[bucket].get(str(category), 0) + int(total)
    return "hour", [LlmUsageTimelineBucket(started_at=key, generation_tokens=value.get("generation", 0), chat_tokens=value.get("chat", 0), total_tokens=sum(value.values())) for key, value in sorted(buckets.items())]
