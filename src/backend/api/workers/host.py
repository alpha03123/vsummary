"""Independent durable Job and Outbox host for Local or Cloud composition."""

from __future__ import annotations

from dataclasses import dataclass

from backend.api.adapters.durable_workspace_index_refresher import (
    submit_workspace_index_event,
    INDEX_CHANGE_EVENTS,
)
from backend.core.request_context import get_workspace_context
from backend.core.context import WorkspaceContext
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


def reconcile_host_jobs(container):
    for job_id, workspace_id in container.job_repository.reconcile_series_batches():
        container.job_repository.finalize_accounting(job_id, workspace_id=workspace_id)
    if container.chat_queue is not None:
        container.chat_queue.reconcile(container.quota_guard, container.usage_store)


def build_worker_host(
    container, *, session_factory, options: WorkerOptions, maintenance=None
) -> WorkerHost:
    def execution_services(workspace_id: str):
        context = get_workspace_context()
        if context is None or context.workspace_id != workspace_id:
            raise RuntimeError("Worker execution context is missing or mismatched.")
        return container.workspace_services_provider.get_services(context)

    def content_changed(event):
        # Events are durable notifications, not process-local cache broadcasts.
        submit_workspace_index_event(repository=container.job_repository, event=event)

    def cleanup_resource(event):
        services = container.workspace_services_provider.get_services(WorkspaceContext(
            workspace_id=event.workspace_id, actor_id="system-worker", request_id=f"outbox:{event.id}"))
        services.linked_series_workspace.delete_resource_files(event.payload)

    def maintain():
        reconcile_host_jobs(container)
        if maintenance is not None:
            maintenance()

    return WorkerHost(
        jobs=SqlJobWorker(
            repository=container.job_repository,
            get_execution_services=execution_services,
            options=options,
            request_limiter=container.request_limiter,
            preference_store=container.preference_store,
            model_profiles=container.model_profiles,
            resource_budget=container.resource_budget,
            maintenance=maintain,
        ),
        outbox=SqlOutboxWorker(
            repository=SqlOutboxRepository(session_factory),
            workspace_id=None,
            handlers={
                **{name: content_changed for name in INDEX_CHANGE_EVENTS},
                "resource_cleanup_requested": cleanup_resource,
            },
        ),
    )
