"""当前内容的 staging 与原子发布。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.video_summary.infrastructure.persistence.ids import new_ulid
from backend.video_summary.infrastructure.persistence.models import (
    Job,
    JobAttempt,
    JobContentStaging,
    JobEvent,
    KnowledgeCard,
    KnowledgeCardSet,
    Mindmap,
    OutboxEvent,
    Summary,
    SummaryChapter,
    Transcript,
    TranscriptSegment,
    Video,
    VideoContentState,
)


class ContentPublishError(RuntimeError):
    """候选内容无法安全发布。"""


@dataclass(frozen=True)
class PublishedContent:
    video_id: str
    content_version: int


class SqlCurrentContentRepository:
    """先写 job staging，再一次事务替换视频当前内容。"""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def stage(
        self,
        *,
        job_id: str,
        video_id: str,
        payload: dict[str, Any],
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> None:
        _validate_payload(payload)
        with self._session_factory.begin() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise ContentPublishError("Cannot stage content for a missing job.")
            if job.resource_id != video_id:
                raise ContentPublishError("Job resource does not match staged video.")
            _require_owned_job(session, job, worker_id=worker_id, lease_token=lease_token)
            existing = session.get(JobContentStaging, job_id)
            if existing is None:
                session.add(JobContentStaging(job_id=job_id, video_id=video_id, payload=payload, state="ready"))
            elif existing.state == "ready" and existing.payload == payload:
                return
            else:
                raise ContentPublishError("Job already has different staged content.")

    def publish(
        self,
        *,
        job_id: str,
        worker_id: str | None = None,
        lease_token: str | None = None,
    ) -> PublishedContent:
        with self._session_factory.begin() as session:
            staged = session.scalar(select(JobContentStaging).where(JobContentStaging.job_id == job_id).with_for_update())
            if staged is None or staged.state != "ready":
                raise ContentPublishError("No ready staged content exists for this job.")
            job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
            video = session.scalar(select(Video).where(Video.id == staged.video_id).with_for_update())
            if job is None or video is None:
                raise ContentPublishError("Staged content references a missing job or video.")
            if job.resource_id != video.id:
                raise ContentPublishError("Job resource does not match staged video.")
            _require_owned_job(session, job, worker_id=worker_id, lease_token=lease_token)
            if job.cancel_requested_at is not None:
                raise ContentPublishError("Cancelled jobs cannot publish content.")

            payload = staged.payload
            _validate_payload(payload)
            version = video.content_version + 1
            _replace_current_content(session, video_id=video.id, content_version=version, payload=payload)
            # Cards and mindmaps depend on transcript/summary content. A newly
            # published content set invalidates them atomically with the switch.
            session.execute(delete(KnowledgeCard).where(KnowledgeCard.video_id == video.id))
            session.execute(delete(KnowledgeCardSet).where(KnowledgeCardSet.video_id == video.id))
            session.execute(delete(Mindmap).where(Mindmap.video_id == video.id))
            video.content_version = version
            state = session.get(VideoContentState, video.id)
            if state is None:
                session.add(
                    VideoContentState(
                        video_id=video.id,
                        content_version=version,
                        transcript_version=version,
                        summary_version=version,
                        cards_version=0,
                        mindmap_version=0,
                    )
                )
            else:
                state.content_version = version
                state.transcript_version = version
                state.summary_version = version
                state.cards_version = 0
                state.mindmap_version = 0
            job.status = "succeeded"
            job.active_key = None
            job.claimed_by = None
            job.lease_token = None
            job.lease_expires_at = None
            job.finished_at = session.scalar(select(func.now()))
            job.result_content_version = version
            if worker_id is not None and lease_token is not None:
                attempt = session.scalar(
                    select(JobAttempt).where(
                        JobAttempt.job_id == job.id,
                        JobAttempt.attempt_no == job.attempt_count,
                        JobAttempt.worker_id == worker_id,
                        JobAttempt.lease_token == lease_token,
                    )
                )
                if attempt is None:
                    raise ContentPublishError("Job attempt is missing.")
                attempt.finished_at = job.finished_at
                attempt.outcome = "succeeded"
            staged.state = "published"
            sequence = (session.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job.id)) or 0) + 1
            session.add(
                JobEvent(
                    id=new_ulid(),
                    job_id=job.id,
                    sequence=sequence,
                    stage="succeeded",
                    progress=100.0,
                    detail="内容已原子发布",
                )
            )
            session.add(
                OutboxEvent(
                    id=new_ulid(),
                    aggregate_type="video_content",
                    aggregate_id=video.id,
                    event_type="content_published",
                    payload={"video_id": video.id, "content_version": version},
                    attempt_count=0,
                )
            )
            return PublishedContent(video_id=video.id, content_version=version)


def _require_owned_job(
    session: Session,
    job: Job,
    *,
    worker_id: str | None,
    lease_token: str | None,
) -> None:
    if (worker_id is None) != (lease_token is None):
        raise ContentPublishError("Worker identity and lease token must be supplied together.")
    if worker_id is None:
        return
    now = session.scalar(select(func.now()))
    if (
        job.status != "running"
        or job.claimed_by != worker_id
        or job.lease_token != lease_token
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        raise ContentPublishError("Worker no longer owns the job lease.")


def _replace_current_content(session: Session, *, video_id: str, content_version: int, payload: dict[str, Any]) -> None:
    transcript = payload["transcript"]
    summary = payload["summary"]
    session.execute(delete(TranscriptSegment).where(TranscriptSegment.video_id == video_id))
    session.execute(delete(SummaryChapter).where(SummaryChapter.video_id == video_id))

    current_transcript = session.get(Transcript, video_id)
    if current_transcript is None:
        current_transcript = Transcript(video_id=video_id)
        session.add(current_transcript)
    current_transcript.content_version = content_version
    current_transcript.language = transcript["language"]
    current_transcript.source_type = transcript["source_type"]
    current_transcript.duration_ms = transcript.get("duration_ms")
    current_transcript.raw_srt_artifact_id = transcript.get("raw_srt_artifact_id")

    current_summary = session.get(Summary, video_id)
    if current_summary is None:
        current_summary = Summary(video_id=video_id)
        session.add(current_summary)
    current_summary.content_version = content_version
    current_summary.title = summary["title"]
    current_summary.markdown = summary["markdown"]
    current_summary.payload = summary["payload"]
    current_summary.content_format_version = summary.get("content_format_version", 1)

    for ordinal, segment in enumerate(transcript["segments"]):
        session.add(
            TranscriptSegment(
                id=new_ulid(),
                video_id=video_id,
                content_version=content_version,
                ordinal=ordinal,
                start_ms=segment["start_ms"],
                end_ms=segment["end_ms"],
                text=segment["text"],
            )
        )
    for ordinal, chapter in enumerate(summary["chapters"]):
        session.add(
            SummaryChapter(
                id=new_ulid(),
                video_id=video_id,
                content_version=content_version,
                ordinal=ordinal,
                title=chapter["title"],
                start_ms=chapter.get("start_ms"),
                end_ms=chapter.get("end_ms"),
                body=chapter["body"],
                payload=chapter.get("payload", {}),
            )
        )


def _validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ContentPublishError("Staged content must be an object.")
    transcript = payload.get("transcript")
    summary = payload.get("summary")
    if not isinstance(transcript, dict) or not isinstance(summary, dict):
        raise ContentPublishError("Staged content requires transcript and summary objects.")
    _require_string(transcript.get("language"), "transcript.language")
    _require_string(transcript.get("source_type"), "transcript.source_type")
    segments = transcript.get("segments")
    if not isinstance(segments, list):
        raise ContentPublishError("transcript.segments must be a list.")
    for segment in segments:
        if not isinstance(segment, dict):
            raise ContentPublishError("Transcript segment must be an object.")
        if not isinstance(segment.get("start_ms"), int) or not isinstance(segment.get("end_ms"), int):
            raise ContentPublishError("Transcript segment timestamps must be integer milliseconds.")
        if segment["start_ms"] < 0 or segment["end_ms"] < segment["start_ms"]:
            raise ContentPublishError("Transcript segment timestamps are invalid.")
        _require_string(segment.get("text"), "transcript segment text")
    _require_string(summary.get("title"), "summary.title")
    if not isinstance(summary.get("markdown"), str):
        raise ContentPublishError("summary.markdown must be a string.")
    if not isinstance(summary.get("payload"), dict):
        raise ContentPublishError("summary.payload must be an object.")
    chapters = summary.get("chapters")
    if not isinstance(chapters, list):
        raise ContentPublishError("summary.chapters must be a list.")
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise ContentPublishError("Summary chapter must be an object.")
        _require_string(chapter.get("title"), "summary chapter title")
        if not isinstance(chapter.get("body"), str):
            raise ContentPublishError("summary chapter body must be a string.")
        for field in ("start_ms", "end_ms"):
            value = chapter.get(field)
            if value is not None and not isinstance(value, int):
                raise ContentPublishError(f"summary chapter {field} must be an integer or null.")


def _require_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContentPublishError(f"{field_name} must be a non-empty string.")
