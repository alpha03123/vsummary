"""MySQL 权威控制面 ORM 模型。

内容表、RAG chunk 与 BlobStore Repository 会在后续阶段加入。本模块先落地
工作区资源、任务、幂等键和 outbox，以消除进程内任务状态作为权威来源。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 VSummary 持久化模型的 Declarative 基类。"""


class TimestampedRow:
    """统一保存 UTC 创建/更新时间；应用层使用 UTC 写入。"""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AppInstallation(TimestampedRow, Base):
    __tablename__ = "app_installations"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    data_format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_import_state: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    legacy_import_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Workspace(TimestampedRow, Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    owner_scope_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Series(TimestampedRow, Base):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("workspace_id", "position", name="uq_series_workspace_position"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    external_source_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Video(TimestampedRow, Base):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("series_id", "external_source_id", name="uq_videos_series_external_source"),
        Index("ix_videos_series_created", "series_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(1_024), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    external_source_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MediaObject(TimestampedRow, Base):
    __tablename__ = "media_objects"
    __table_args__ = (UniqueConstraint("blob_key", name="uq_media_objects_blob_key"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="RESTRICT"), nullable=False, index=True)
    blob_key: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)


class Artifact(TimestampedRow, Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("blob_key", name="uq_artifacts_blob_key"),
        Index("ix_artifacts_video_kind", "video_id", "kind"),
        Index("ix_artifacts_series_kind", "series_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id", ondelete="RESTRICT"), nullable=True)
    series_id: Mapped[str | None] = mapped_column(ForeignKey("series.id", ondelete="RESTRICT"), nullable=True)
    content_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    blob_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)


class VideoContentState(TimestampedRow, Base):
    __tablename__ = "video_content_state"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    transcript_version: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    cards_version: Mapped[int] = mapped_column(Integer, nullable=False)
    mindmap_version: Mapped[int] = mapped_column(Integer, nullable=False)


class Transcript(TimestampedRow, Base):
    __tablename__ = "transcripts"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_srt_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="RESTRICT"), nullable=True
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("video_id", "content_version", "ordinal", name="uq_transcript_segments_version_ordinal"),
        Index("ix_transcript_segments_video_time", "video_id", "start_ms"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class Summary(TimestampedRow, Base):
    __tablename__ = "summaries"

    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1_024), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_format_version: Mapped[int] = mapped_column(Integer, nullable=False)


class SummaryChapter(Base):
    __tablename__ = "summary_chapters"
    __table_args__ = (
        UniqueConstraint("video_id", "content_version", "ordinal", name="uq_summary_chapters_version_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1_024), nullable=False)
    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class JobContentStaging(TimestampedRow, Base):
    __tablename__ = "job_content_staging"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class LegacyImportItem(TimestampedRow, Base):
    __tablename__ = "legacy_import_items"
    __table_args__ = (UniqueConstraint("source_kind", "source_key", name="uq_legacy_import_source"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class KnowledgeCardSet(TimestampedRow, Base):
    __tablename__ = "knowledge_card_sets"
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1_024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class KnowledgeCard(Base):
    __tablename__ = "knowledge_cards"
    __table_args__ = (UniqueConstraint("video_id", "ordinal", name="uq_knowledge_cards_video_ordinal"),)
    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1_024), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    related_card_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class Mindmap(TimestampedRow, Base):
    __tablename__ = "mindmaps"
    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=True, unique=True)
    series_id: Mapped[str | None] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), nullable=True, unique=True)
    content_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(1_024), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)


class Job(TimestampedRow, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("active_key", name="uq_jobs_active_key"),
        Index("ix_jobs_claim", "status", "lease_expires_at", "created_at"),
        Index("ix_jobs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(26), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_content_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_no", name="uq_job_attempts_number"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class IdempotencyKey(TimestampedRow, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope_id", "key", name="uq_idempotency_scope_key"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_job_events_sequence"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[float | None] = mapped_column(nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_delivery", "delivered_at", "claimed_at", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
