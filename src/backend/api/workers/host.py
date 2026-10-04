"""Independent durable Job and Outbox host for Local or Cloud composition."""

from __future__ import annotations

from dataclasses import dataclass

from backend.api.adapters.durable_workspace_index_refresher import (
    submit_workspace_index_refresh,
)
from backend.core.request_context import get_workspace_context
from backend.video_summary.infrastructure.persistence.job_worker import (
    SqlJobWorker,
    WorkerOptions,
)
from backend.video_summary.infrastructure.persistence.outbox_repository import (
    SqlOutboxRepository,
)
from backend.video_summary.infrastructure.persistence.outbox_worker import (
    SqlOutboxWorker,
)


@dataclass
class WorkerHost:
    jobs: SqlJobWorker
    outbox: SqlOutboxWorker

    def start(self):
        self.outbox.start()
        self.jobs.start()

    def stop(self):
        self.jobs.stop()
        self.outbox.stop()


def build_worker_host(
    container, *, session_factory, options: WorkerOptions
) -> WorkerHost:
    def execution_services(workspace_id: str):
        context = get_workspace_context()
        if context is None or context.workspace_id != workspace_id:
            raise RuntimeError("Worker execution context is missing or mismatched.")
        return container.workspace_services_provider.get_services(context)

    def content_changed(event):
        # Events are durable notifications, not process-local cache broadcasts.
        submit_workspace_index_refresh(
            repository=container.job_repository, workspace_id=event.workspace_id
        )

    return WorkerHost(
        jobs=SqlJobWorker(
            repository=container.job_repository,
            get_execution_services=execution_services,
            options=options,
            request_limiter=container.request_limiter,
        ),
        outbox=SqlOutboxWorker(
            repository=SqlOutboxRepository(session_factory),
            workspace_id=None,
            handlers={
                name: content_changed
                for name in (
                    "content_published",
                    "note_published",
                    "knowledge_cards_published",
                )
            },
        ),
    )
