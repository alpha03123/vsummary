from datetime import datetime, timezone
from types import SimpleNamespace as Item
from backend.api.adapters.job_status import durable_status


def test_batch_averages_child_progress_and_restores_current_child_history():
    now = datetime.now(timezone.utc)
    parent = Item(id='parent', status='waiting_children', cancel_requested=False, failure_detail=None, started_at=now)
    children = [Item(id='done', status='succeeded'), Item(id='active', status='running'), Item(id='queued', status='queued')]
    def event(stage, progress):
        return Item(status='running', stage=stage, progress=progress, detail=stage, occurred_at=now)
    histories = {'parent': [event('waiting_children', 0)], 'done': [event('publish', 99)],
        'active': [event('transcribe', 50), event('generate_ai_summary', None)], 'queued': []}
    class Repository:
        def latest_for_resource(self, **kwargs): return parent
        def children(self, *args, **kwargs): return children
        def events(self, job_id, **kwargs): return histories[job_id]
    snapshot = durable_status(Repository(), workspace_id='workspace', resource_id='series', operations=('generate_series_batch',), batch=True)
    assert snapshot['progress'] == 50
    assert snapshot['stage'] == 'generate_ai_summary'
    assert snapshot['finished'] == 1
    assert [event['stage'] for event in snapshot['events']] == ['transcribe', 'generate_ai_summary']
