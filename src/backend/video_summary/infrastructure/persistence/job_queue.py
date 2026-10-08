"""Optional single-host admission and fair scheduling for SQL jobs."""
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock
from sqlalchemy import func, select

from backend.core.job_queue import JobQueueFull
from backend.video_summary.infrastructure.persistence.models import Job


class SqlJobQueuePolicy:
    def __init__(self, sessions, *, lock_path: Path, capacity: int, per_actor: int):
        if not 0 < per_actor <= capacity:
            raise ValueError("Job queue limits require 0 < per_actor <= capacity.")
        self.sessions, self.capacity, self.per_actor = sessions, capacity, per_actor
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = lock_path

    def lock(self):
        return FileLock(str(self.lock_path))

    @contextmanager
    def admit(self, *, actor_id, units):
        # Hold the same host lock until the caller commits its job insert.
        with self.lock(), self.sessions() as session:
            roots = session.scalars(select(Job).where(
                Job.parent_job_id.is_(None), Job.actor_id.is_not(None),
                Job.resource_type.in_(("video", "series")),
                Job.status.in_(("queued", "retrying", "running", "cancelling", "waiting_children")),
            )).all()
            total = own = 0
            for job in roots:
                weight = max(1, job.request_payload.get("_usage_estimate", {}).get("units", 1)) if job.operation == "generate_series_batch" else 1
                total += weight
                if job.actor_id == actor_id:
                    own += weight
            if own + units > self.per_actor:
                raise JobQueueFull(f"你的待处理任务较多，每个账号最多同时提交 {self.per_actor} 个视频，请等待部分任务完成后再试。")
            if total + units > self.capacity:
                raise JobQueueFull("当前处理队列已满，请稍后重试。")
            yield

    @staticmethod
    def scheduling_order():
        # Prefer an actor with fewer running jobs, then the least recently served.
        # The claim lock serializes this decision across workers on the same host.
        history = Job.__table__.alias("actor_job_history")
        running = select(func.count()).where(
            history.c.actor_id == Job.actor_id,
            history.c.status.in_(("running", "cancelling")),
            history.c.operation != "generate_series_batch",
        ).scalar_subquery()
        served = select(func.max(history.c.started_at)).where(
            history.c.actor_id == Job.actor_id,
            history.c.operation != "generate_series_batch",
        ).scalar_subquery()
        return running, served, Job.available_at, Job.created_at, Job.id
