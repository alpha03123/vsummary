from datetime import datetime,timezone,timedelta
from dataclasses import asdict
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
import asyncio
import json
import shutil
from pathlib import Path
import pytest
from sqlalchemy import select,text
from backend.core.ids import new_ulid
from backend.core.context import WorkspaceContext
from backend.core.request_context import bind_workspace_context
from backend.core.preferences import bind_user_preferences
from backend.core.metering import bind_resource_budget
from backend.core.quota import QuotaReservation
from backend.core.chat_queue import SqlChatQueue,ChatQueueFull,ChatRequestCancelled
from backend.core.job_queue import SqlJobQueuePolicy, JobQueueFull
from backend.shared.llm.usage import MySqlLlmUsageStore,LlmUsageRecord
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from backend.video_summary.infrastructure.persistence.job_worker import SqlJobWorker, WorkerOptions
from backend.video_summary.infrastructure.persistence.job_worker import SqlJobProgressReporter
from backend.local.composition import build_local_container
from backend.local.routes.settings import update_workspace_settings
from backend.api.schemas.contracts import UpdateWorkspaceSettingsRequest
from backend.video_summary.infrastructure.config.settings import load_settings, replace_video_generation_concurrency, save_settings
from backend.video_summary.infrastructure.persistence.models import Job,Video,Summary


def test_processed_linked_video_stays_readable_after_media_cleanup(stored_video,mysql_sessions):
    workspace,series,video=stored_video
    with mysql_sessions.begin() as session:
        session.execute(text("UPDATE videos SET source_kind='bilibili',content_version=1 WHERE id=:video"), {'video':video})
        session.add(Summary(video_id=video,content_version=1,title='Video',markdown='Generated summary',
            payload={'title':'Video','chapters':[]},content_format_version=1))
        session.execute(text("DELETE FROM media_objects WHERE video_id=:video"), {'video':video})
    card=next(item for group in workspace.list_series() for item in group.videos if item.id==video)
    assert card.processed
    assert card.status=='ready'
    assert not card.is_linked


class Guard:
    def __init__(self):
        self.attempts=0;self.charges=set();self.records=[]
    def reserve_job(self,*args):
        return QuotaReservation(new_ulid())
    def release(self,*args):
        pass
    def settle(self,reservation,actual):
        self.attempts+=1
        if self.attempts==1:
            raise RuntimeError('temporary settlement failure')
        self.charges.add(reservation);self.records.append(actual)


def test_accounting_retries_after_failure_and_contains_real_measurements(stored_video,mysql_sessions):
    workspace,series,video=stored_video
    context=WorkspaceContext(workspace.workspace_id,new_ulid(),new_ulid())
    guard=Guard()
    repository=SqlJobRepository(mysql_sessions,quota_guard=guard)
    with mysql_sessions.begin() as session:
        session.get(Video,video).duration_ms=60000
    with bind_workspace_context(context),bind_user_preferences({'ai_summary_multimodal_enabled':True}):
        job=repository.submit(workspace_id=context.workspace_id,resource_type='video',resource_id=video,operation='generate_summary',
            request_payload={'series_id':series},active_key='test:'+video,idempotency_scope_id=context.workspace_id,idempotency_key='same')
        replay=repository.submit(workspace_id=context.workspace_id,resource_type='video',resource_id=video,operation='generate_summary',
            request_payload={'series_id':series},active_key='test:'+video,idempotency_scope_id=context.workspace_id,idempotency_key='same')
        assert replay.id==job.id and not replay.created
        with bind_resource_budget(None,job.id):
            MySqlLlmUsageStore(mysql_sessions).record(LlmUsageRecord(datetime.now(timezone.utc),'generation','openai','','model',30,10,40))
    with mysql_sessions.begin() as session:
        row=session.get(Job,job.id);row.status='succeeded';row.active_key=None
        assert row.request_payload['_user_preferences']['ai_summary_multimodal_enabled'] is True
    with pytest.raises(RuntimeError):
        repository.finalize_accounting(job.id,workspace_id=context.workspace_id)
    assert repository.get(job.id).accounting_status=='pending'
    repository.finalize_accounting(job.id,workspace_id=context.workspace_id)
    repository.finalize_accounting(job.id,workspace_id=context.workspace_id)
    assert len(guard.charges)==1 and guard.attempts==2
    actual=guard.records[0]
    assert actual.multimodal_enabled is True
    assert (actual.duration_seconds,actual.input_tokens,actual.output_tokens)==(60,30,10)
    assert repository.get(job.id).accounting_status=='settled'
    assert repository.list_jobs(workspace_id=context.workspace_id,actor_id=context.actor_id)['total']==1
    assert repository.list_jobs(workspace_id=context.workspace_id,actor_id=new_ulid())['total']==0


def test_chat_queue_is_bounded_and_prevents_one_actor_from_occupying_all_slots(mysql_sessions):
    queue=SqlChatQueue(mysql_sessions,capacity=2,waiting_limit=3,per_actor_waiting=1)
    a=WorkspaceContext(new_ulid(),new_ulid(),new_ulid());b=WorkspaceContext(new_ulid(),new_ulid(),new_ulid())
    first,second,third=new_ulid(),new_ulid(),new_ulid()
    try:
        queue.enqueue(a,first);assert queue.try_start(a,first)
        queue.enqueue(a,second);queue.enqueue(b,third)
        assert not queue.try_start(a,second)
        assert queue.try_start(b,third)
        assert queue.get(b,second) is None
        with pytest.raises(ChatQueueFull):
            queue.enqueue(a,new_ulid())
        queue.finish(first,'succeeded')
        assert queue.try_start(a,second)
        queue.cancel(a,second)
        with pytest.raises(ChatRequestCancelled):
            queue.try_start(a,second)
    finally:
        with mysql_sessions.begin() as session:
            session.execute(text('DELETE FROM chat_requests WHERE actor_id IN (:a,:b)'),{'a':a.actor_id,'b':b.actor_id})


def test_chat_accounting_recovers_and_persists_measured_usage_in_mysql(stored_video, mysql_sessions):
    workspace, _, _ = stored_video
    context = WorkspaceContext(workspace.workspace_id, new_ulid(), new_ulid())
    operation, reservation = new_ulid(), new_ulid()
    queue, guard = SqlChatQueue(mysql_sessions), Guard()
    store = MySqlLlmUsageStore(mysql_sessions)
    queue.enqueue(context, operation)
    queue.attach_reservation(operation, reservation, 'luna')
    with bind_workspace_context(context), bind_resource_budget(None, operation):
        store.record(LlmUsageRecord(datetime.now(timezone.utc),'chat','openai','','model',30,10,40))
    queue.finish(operation, 'succeeded')
    with pytest.raises(RuntimeError, match='temporary settlement failure'):
        queue.account(operation, guard, store)
    queue.reconcile(guard, store)
    queue.account(operation, guard, store)
    assert guard.attempts == 2
    assert guard.records[0].input_tokens == 30
    assert guard.records[0].output_tokens == 10
    with mysql_sessions() as session:
        row = session.execute(text('SELECT accounting_status,`usage` FROM chat_requests WHERE id=:id'), {'id': operation}).mappings().one()
        assert row['accounting_status'] == 'settled'
        assert json.loads(row['usage']) == {'input_tokens': 30, 'output_tokens': 10}


def test_series_parent_waits_for_children_then_has_one_terminal_outcome(stored_video, mysql_sessions):
    workspace, series_id, video_id = stored_video
    repository = SqlJobRepository(mysql_sessions)
    parent_id, child_id = new_ulid(), new_ulid()
    with mysql_sessions.begin() as session:
        session.add(Job(id=parent_id, workspace_id=workspace.workspace_id, resource_type='series',
            resource_id=series_id, operation='generate_series_batch', status='waiting_children',
            request_payload={}, active_key='series:'+series_id+':generate_series_batch'))
        session.add(Job(id=child_id, workspace_id=workspace.workspace_id, parent_job_id=parent_id,
            resource_type='video', resource_id=video_id, operation='generate_summary', status='queued', request_payload={}))
    assert repository.reconcile_series_batches() == []
    assert repository.get(parent_id, workspace_id=workspace.workspace_id).status == 'waiting_children'
    with mysql_sessions.begin() as session:
        session.get(Job, child_id).status = 'succeeded'
    assert (parent_id, workspace.workspace_id) in repository.reconcile_series_batches()
    parent = repository.get(parent_id, workspace_id=workspace.workspace_id)
    assert parent.status == 'succeeded'
    assert repository.active_for_resource(workspace_id=workspace.workspace_id, resource_id=series_id,
        operation='generate_series_batch') is None
    events = len(repository.events(parent_id, after_sequence=0, workspace_id=workspace.workspace_id))
    assert repository.reconcile_series_batches() == []
    assert len(repository.events(parent_id, after_sequence=0, workspace_id=workspace.workspace_id)) == events


def test_series_cancellation_stays_pending_until_children_are_terminal(stored_video, mysql_sessions):
    workspace, series_id, video_id = stored_video
    repository = SqlJobRepository(mysql_sessions)
    parent_id, child_id = new_ulid(), new_ulid()
    with mysql_sessions.begin() as session:
        session.add(Job(id=parent_id, workspace_id=workspace.workspace_id, resource_type='series',
            resource_id=series_id, operation='generate_series_batch', status='waiting_children',
            request_payload={}, active_key='series:'+series_id+':generate_series_batch'))
        session.add(Job(id=child_id, workspace_id=workspace.workspace_id, parent_job_id=parent_id,
            resource_type='video', resource_id=video_id, operation='generate_summary', status='queued', request_payload={}))
    cancelled = repository.request_cancel_series_generation(workspace_id=workspace.workspace_id, series_id=series_id)
    assert cancelled[0].status == 'cancelling'
    assert repository.get(child_id, workspace_id=workspace.workspace_id).status == 'cancelled'
    assert (parent_id, workspace.workspace_id) in repository.reconcile_series_batches()
    assert repository.get(parent_id, workspace_id=workspace.workspace_id).status == 'cancelled'


def test_unfinished_old_batches_do_not_block_ready_batches(stored_video, mysql_sessions):
    workspace, series_id, video_id = stored_video
    repository = SqlJobRepository(mysql_sessions)
    parent_id, child_id = new_ulid(), new_ulid()
    with mysql_sessions.begin() as session:
        session.add(Job(id=parent_id, workspace_id=workspace.workspace_id, resource_type='series',
            resource_id=series_id, operation='generate_series_batch', status='waiting_children',
            request_payload={}, active_key=None))
        session.add(Job(id=child_id, workspace_id=workspace.workspace_id, parent_job_id=parent_id,
            resource_type='video', resource_id=video_id, operation='generate_summary', status='running', request_payload={}))
    ready_id = new_ulid()
    with mysql_sessions.begin() as session:
        session.add(Job(id=ready_id, workspace_id=workspace.workspace_id, resource_type='series',
            resource_id=series_id, operation='generate_series_batch', status='waiting_children', request_payload={}))
        session.add(Job(id=new_ulid(), workspace_id=workspace.workspace_id, parent_job_id=ready_id,
            resource_type='video', resource_id=video_id, operation='generate_summary', status='succeeded', request_payload={}))
    assert repository.reconcile_series_batches(limit=1) == [(ready_id, workspace.workspace_id)]
    assert repository.get(parent_id).status == 'waiting_children'


def test_job_admission_is_atomic_across_concurrent_submitters(stored_video, mysql_sessions, tmp_path):
    workspace, _, video = stored_video
    actor = new_ulid()
    queue = SqlJobQueuePolicy(mysql_sessions, lock_path=tmp_path/'queue.lock', capacity=10000, per_actor=1)
    barrier = Barrier(2)
    def submit():
        barrier.wait()
        try:
            with queue.admit(actor_id=actor, units=1), mysql_sessions.begin() as session:
                session.add(Job(id=new_ulid(), workspace_id=workspace.workspace_id, actor_id=actor,
                    resource_type='video', resource_id=video, operation='test-admission', status='queued', request_payload={}))
            return 'accepted'
        except JobQueueFull:
            return 'full'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: submit(), range(2))) == ['accepted', 'full']
    with pytest.raises(JobQueueFull):
        with queue.admit(actor_id=new_ulid(), units=2):
            pytest.fail('Oversized series must be rejected before submission.')
    with mysql_sessions() as session:
        roots = session.scalars(select(Job).where(Job.parent_job_id.is_(None),
            Job.actor_id.is_not(None), Job.resource_type.in_(("video", "series")),
            Job.status.in_(("queued", "retrying", "running", "cancelling", "waiting_children")))).all()
        used = sum(max(1, job.request_payload.get('_usage_estimate', {}).get('units', 1))
            if job.operation == 'generate_series_batch' else 1 for job in roots)
    full_queue = SqlJobQueuePolicy(mysql_sessions, lock_path=tmp_path/'queue.lock', capacity=used, per_actor=1)
    with pytest.raises(JobQueueFull, match='当前处理队列已满'):
        with full_queue.admit(actor_id=new_ulid(), units=1):
            pytest.fail('A different actor must also respect global capacity.')


def test_job_claim_serves_another_actor_before_the_first_actors_backlog(stored_video, mysql_sessions, tmp_path):
    workspace, _, video = stored_video
    actor_a, actor_b, operation = new_ulid(), new_ulid(), new_ulid()
    queue = SqlJobQueuePolicy(mysql_sessions, lock_path=tmp_path/'queue.lock', capacity=100, per_actor=50)
    repository = SqlJobRepository(mysql_sessions, queue_policy=queue)
    jobs = [new_ulid() for _ in range(3)]
    with mysql_sessions.begin() as session:
        for index, (job_id, actor) in enumerate(zip(jobs, (actor_a, actor_a, actor_b))):
            session.add(Job(id=job_id, workspace_id=workspace.workspace_id, actor_id=actor,
                resource_type='video', resource_id=video, operation=operation, status='queued', request_payload={},
                created_at=datetime.now(timezone.utc)-timedelta(seconds=60-index),
                available_at=datetime.now(timezone.utc)-timedelta(seconds=60-index)))
    first = repository.claim(worker_id='one', lease_seconds=120, operations=frozenset({operation}))
    second = repository.claim(worker_id='two', lease_seconds=120, operations=frozenset({operation}))
    assert first.id == jobs[0]
    assert second.id == jobs[2]
    repository.succeed(first, detail='done')
    repository.succeed(second, detail='done')
    assert repository.claim(worker_id='one', lease_seconds=120, operations=frozenset({operation})).id == jobs[1]


def test_two_workers_execute_while_maintenance_keeps_running(stored_video, mysql_sessions):
    workspace, _, video = stored_video
    operation = new_ulid()
    repository = SqlJobRepository(mysql_sessions)
    with mysql_sessions.begin() as session:
        for _ in range(2):
            session.add(Job(id=new_ulid(), workspace_id=workspace.workspace_id,
                resource_type='video', resource_id=video, operation=operation, status='queued', request_payload={}))
    entered, release, maintained = Event(), Event(), Event()
    gate, active = Lock(), []
    async def handler(claim, reporter):
        with gate:
            active.append(claim.id)
            if len(active) == 2:
                entered.set()
        await asyncio.to_thread(release.wait, 5)
    def maintain():
        if entered.is_set() and not release.is_set():
            maintained.set()
    worker = SqlJobWorker(repository=repository,
        get_execution_services=lambda _: SimpleNamespace(job_operation_handlers={operation: handler}),
        options=WorkerOptions(worker_id='parallel-test', concurrency=2, maintenance_seconds=.05,
            operation_filter=frozenset({operation})), maintenance=maintain)
    worker.start()
    try:
        assert entered.wait(3), 'Both execution slots must start without waiting for the other task.'
        assert maintained.wait(2), 'Maintenance must continue while both execution slots are occupied.'
    finally:
        release.set()
        worker.stop()
    assert all(repository.get(job_id).status == 'succeeded' for job_id in active)


def test_local_settings_control_worker_concurrency_at_startup_and_runtime(stored_video, mysql_sessions, tmp_path):
    workspace, _, video_id = stored_video
    config_path = tmp_path / 'config' / 'settings.toml'
    config_path.parent.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[4] / 'config/settings.toml.example',
        config_path.parent / 'settings.toml.example')
    settings = load_settings(config_path, tmp_path)
    save_settings(config_path, replace_video_generation_concurrency(settings, 2))
    container = build_local_container(tmp_path, workspace=workspace)
    assert container.job_worker.concurrency == 2
    entered, release, increased = Event(), Event(), Event()
    gate, active = Lock(), []
    context = container.context_provider.get_context(request_id='local-concurrency')
    services = container.workspace_services_provider.get_services(context)

    async def handler(claim, _reporter):
        with gate:
            active.append(claim.id)
            if len(active) == 2:
                entered.set()
            if len(active) == 3:
                increased.set()
        await asyncio.to_thread(release.wait, 5)

    services.job_operation_handlers['generate_video_mindmap'] = handler
    with mysql_sessions.begin() as session:
        for _ in range(3):
            session.add(Job(id=new_ulid(), workspace_id=workspace.workspace_id,
                resource_type='video', resource_id=video_id, operation='generate_video_mindmap',
                status='queued', request_payload={}))
    container.job_worker.start()
    try:
        assert entered.wait(3)
        assert not increased.is_set()
        request = UpdateWorkspaceSettingsRequest.model_validate({
            **asdict(container.settings_service.get_workspace_settings()),
            'video_generation_concurrency': 3,
        })
        asyncio.run(update_workspace_settings(request=request, container=container, services=services))
        assert increased.wait(3)
        assert container.job_worker.concurrency == 3
        assert load_settings(config_path, tmp_path).generation.video_generation_concurrency == 3
    finally:
        release.set()
        container.job_worker.stop()
    assert all(container.job_repository.get(job_id).status == 'succeeded' for job_id in active)


def test_retrying_series_dispatch_reuses_children_and_keeps_waiting(stored_video, mysql_sessions, tmp_path):
    workspace, series_id, _ = stored_video
    (tmp_path/'config').mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[4]/'config/settings.toml.example',
        tmp_path/'config/settings.toml.example')
    container = build_local_container(tmp_path, workspace=workspace)
    repository = container.job_repository
    context = container.context_provider.get_context(request_id='retry-dispatch')
    handler = container.workspace_services_provider.get_services(context).job_operation_handlers['generate_series_batch']
    parent_id = new_ulid()
    with mysql_sessions.begin() as session:
        session.add(Job(id=parent_id, workspace_id=workspace.workspace_id, resource_type='series',
            resource_id=series_id, operation='generate_series_batch', status='queued',
            request_payload={'processing_mode': 'summary'}, active_key='retry-dispatch:'+parent_id))
    try:
        with bind_workspace_context(context):
            for attempt in range(2):
                claim = repository.claim(worker_id='dispatch-retry', lease_seconds=120,
                    operations=frozenset({'generate_series_batch'}))
                assert claim.id == parent_id
                assert asyncio.run(handler(claim, SqlJobProgressReporter(repository, claim))) is False
                assert repository.get(parent_id).status == 'waiting_children'
                assert len(repository.children(parent_id, workspace_id=workspace.workspace_id)) == 1
                if attempt == 0:
                    with mysql_sessions.begin() as session:
                        session.get(Job, parent_id).status = 'retrying'
    finally:
        container.model_http_client.close()


def test_series_with_missing_media_fails_instead_of_succeeding_with_zero_children(stored_video, mysql_sessions, tmp_path):
    workspace, series_id, video = stored_video
    workspace.get_video_source(series_id, video).source_path.unlink()
    (tmp_path/'config').mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[4]/'config/settings.toml.example',
        tmp_path/'config/settings.toml.example')
    container = build_local_container(tmp_path, workspace=workspace)
    repository = container.job_repository
    parent_id = new_ulid()
    with mysql_sessions.begin() as session:
        session.add(Job(id=parent_id, workspace_id=workspace.workspace_id, resource_type='series',
            resource_id=series_id, operation='generate_series_batch', status='queued',
            request_payload={'processing_mode': 'summary'}))
    claim = repository.claim(worker_id='missing-media', lease_seconds=120,
        operations=frozenset({'generate_series_batch'}))
    context = container.context_provider.get_context(request_id='missing-media')
    worker = SqlJobWorker(repository=repository,
        get_execution_services=lambda _: container.workspace_services_provider.get_services(context),
        options=WorkerOptions(worker_id='missing-media'))
    try:
        asyncio.run(worker._execute(claim))
        snapshot = repository.get(parent_id)
        assert snapshot.status == 'failed'
        assert snapshot.failure_code == 'media_source_unavailable'
        assert '重新上传' in snapshot.failure_detail
        assert repository.children(parent_id, workspace_id=workspace.workspace_id) == []
    finally:
        container.model_http_client.close()
