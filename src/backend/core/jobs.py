"""Stable job presentation contract for host task centres."""
from datetime import timezone


def job_snapshot_payload(snapshot):
    def timestamp(value):
        return value.replace(tzinfo=timezone.utc).timestamp() if value is not None else None
    return {'job_id':snapshot.id,'workspace_id':snapshot.workspace_id,'actor_id':snapshot.actor_id,
            'parent_job_id':snapshot.parent_job_id,'resource':{'type':snapshot.resource_type,'id':snapshot.resource_id},
            'operation':snapshot.operation,'status':snapshot.status,'attempt_count':snapshot.attempt_count,
            'max_attempts':snapshot.max_attempts,'cancel_requested':snapshot.cancel_requested,
            'failure_code':snapshot.failure_code,'failure_detail':snapshot.failure_detail,
            'result_content_version':snapshot.result_content_version,
            'created_at':snapshot.created_at.replace(tzinfo=timezone.utc).isoformat() if snapshot.created_at is not None else None,
            'started_at':timestamp(snapshot.started_at),'finished_at':timestamp(snapshot.finished_at),
            'accounting_status':snapshot.accounting_status}
