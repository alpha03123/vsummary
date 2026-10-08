import asyncio
from dataclasses import replace
from pathlib import Path
from shutil import copyfile

import pytest
from PIL import Image
from unittest.mock import AsyncMock
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from backend.api.di.bootstrap import build_api_container
from backend.core.capabilities import CapabilitySet
from backend.core.quota import UnlimitedQuotaGuard, NoopUsageMeter
from backend.local.composition import LocalWorkspaceContextProvider, LocalWorkspaceServicesProvider
from backend.local.composition import build_local_container
from backend.video_summary.infrastructure.media_tools import FfmpegMediaProcessor
from backend.video_summary.infrastructure.config.settings import load_settings, save_settings
from backend.video_summary.library.models import KnowledgeCardDTO, GeneratedVideoAiNoteDTO
from backend.video_summary.library.markdown_exports import render_transcript_markdown
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from backend.video_summary.infrastructure.persistence.execution_context import bind_execution_claim
from backend.video_summary.infrastructure.persistence.models import Job
from sqlalchemy import select, event
from backend.core.errors import ActiveJobConflictError
from backend.video_summary.infrastructure.persistence.models import Video


@pytest.fixture(autouse=True)
def cancel_test_background_jobs(stored_video,mysql_sessions):
    yield
    workspace=stored_video[0]
    repository=SqlJobRepository(mysql_sessions)
    with mysql_sessions() as session:
        job_ids=session.scalars(select(Job.id).where(Job.workspace_id==workspace.workspace_id,
            Job.status.in_(('queued','retrying','running','cancelling')))).all()
    for job_id in job_ids:
        repository.request_cancel(job_id,workspace_id=workspace.workspace_id)
from tests.backend.integration.persistence.test_generation_stage_cache import Pipeline


class MindmapGenerator:
    def __init__(self,workspace):
        self.workspace=workspace

    async def run(self,*,series_id,video_id,**_kwargs):
        self.workspace.save_video_mindmap(series_id,video_id,mindmap={'id':'root','title':'Automatic map','children':[]})


class CardGenerator:
    def __init__(self,fail):
        self.fail=fail

    async def arun(self,**_kwargs):
        if self.fail:
            raise RuntimeError('Injected card failure')
        return [KnowledgeCardDTO('generated-card','Automatic card','concept','Summary','Details',[],[],[])]


@pytest.mark.parametrize('mode,fail_cards', [('summary',False),('summary',True),('transcript',False)])
def test_durable_generation_runs_automatic_artifacts_and_preserves_failures(stored_video,mysql_sessions,tmp_path,mode,fail_cards):
    workspace,series_id,video_id=stored_video
    pipeline=Pipeline(stored_video,tmp_path/'pipeline')
    config=tmp_path/'config/settings.toml'
    config.parent.mkdir()
    copyfile(Path(__file__).resolve().parents[4]/'config/settings.toml.example',config)
    settings=load_settings(config,tmp_path)
    save_settings(config,replace(settings,generation=replace(settings.generation,
        auto_generate_artifacts=('mindmap','knowledge_cards'),mindmap_visual_input='none',cards_visual_input='none')))
    provider=LocalWorkspaceServicesProvider(workspace_id=workspace.workspace_id)
    container,services=build_api_container(tmp_path,workspace_override=workspace,generator=pipeline.generator,
        mindmap_generator=MindmapGenerator(workspace),knowledge_card_generator=CardGenerator(fail_cards),
        context_provider=LocalWorkspaceContextProvider(workspace_id=workspace.workspace_id),
        workspace_services_provider=provider,quota_guard=UnlimitedQuotaGuard(),usage_meter=NoopUsageMeter(),
        capabilities=CapabilitySet())
    provider.install_services(services)
    operation='generate_summary' if mode=='summary' else 'generate_transcript'
    submitted=container.job_repository.submit(workspace_id=workspace.workspace_id,resource_type='video',resource_id=video_id,
        operation=operation,request_payload={'series_id':series_id,'processing_mode':mode},active_key='automatic:'+video_id,
        idempotency_scope_id=None,idempotency_key=None)
    claim=container.job_repository.claim(worker_id='automatic',lease_seconds=120,operations=frozenset({operation}))
    asyncio.run(container.job_worker._execute(claim))
    assert container.job_repository.get(submitted.id).status == 'succeeded'
    mindmap=workspace.get_video_mindmap(series_id,video_id)
    cards=workspace.get_video_knowledge_cards(series_id,video_id)
    if mode=='summary':
        assert mindmap is not None
        assert bool(cards and cards.cards) is not fail_cards
        events=container.job_repository.events(submitted.id,after_sequence=0,workspace_id=workspace.workspace_id)
        if fail_cards:
            assert 'knowledge_cards' in events[-1].detail
        assert workspace.get_video_summary(series_id,video_id) is not None
    else:
        assert mindmap is None
        assert not cards or not cards.cards
        assert workspace.get_video_summary(series_id,video_id) is None
        card=next(video for series in workspace.list_series() for video in series.videos if video.id==video_id)
        assert card.has_transcript and not card.processed
        workspace.update_video_transcript(series_id,video_id,markdown=render_transcript_markdown({
            'title':'Video','segments':[{'start_seconds':0,'end_seconds':3,'text':'Edited transcript'}]}))
        assert workspace.get_video_summary(series_id,video_id) is None


def test_durable_retry_reuses_completed_transcription(stored_video,mysql_sessions,tmp_path):
    workspace,series_id,video_id=stored_video
    repository=SqlJobRepository(mysql_sessions)

    def claim():
        repository.submit(workspace_id=workspace.workspace_id,resource_type='video',resource_id=video_id,
            operation='generate_summary',request_payload={'series_id':series_id,'processing_mode':'summary'},
            active_key='retry:'+video_id,idempotency_scope_id=None,idempotency_key=None)
        return repository.claim(worker_id='retry',lease_seconds=120,operations=frozenset({'generate_summary'}))

    first=Pipeline(stored_video,tmp_path/'first',outcome='failed')
    initial=claim()
    with bind_execution_claim(initial),pytest.raises(RuntimeError):
        asyncio.run(first.generator.run(series_id=series_id,video_id=video_id,job_id=initial.id,
            worker_id=initial.worker_id,lease_token=initial.lease_token))
    repository.fail(initial,failure_code='internal_error',failure_detail='Injected failure',retry_delay_seconds=None)
    assert first.asr.calls == 1
    second=Pipeline(stored_video,tmp_path/'second')
    retry=claim()
    with bind_execution_claim(retry):
        asyncio.run(second.generator.run(series_id=series_id,video_id=video_id,job_id=retry.id,
            worker_id=retry.worker_id,lease_token=retry.lease_token))
    repository.succeed(retry,detail='saved')
    assert second.asr.calls == 0
    assert workspace.get_video_summary(series_id,video_id) is not None


def test_regenerated_ai_summary_images_are_available_from_artifact_store(stored_video,tmp_path,monkeypatch):
    workspace,series_id,video_id=stored_video
    Pipeline(stored_video,tmp_path/'seed').run()
    config=tmp_path/'config/settings.toml'
    config.parent.mkdir()
    copyfile(Path(__file__).resolve().parents[4]/'config/settings.toml.example',config)
    container=build_local_container(tmp_path,workspace=workspace)
    context=container.context_provider.get_context(request_id='note-images')
    services=container.workspace_services_provider.get_services(context)
    generator=services.generate_video_ai_summary._generator
    monkeypatch.setattr(generator,'arun_ai_summary',AsyncMock(return_value=GeneratedVideoAiNoteDTO(
        content='Generated note\n[[IMG:1]]',note_visual_mode='screenshots',note_max_images=2,note_image_min_gap_seconds=0)))
    monkeypatch.setattr(FfmpegMediaProcessor,'probe_duration',lambda self,path:3.0)

    def extract(self,path,seconds,target):
        Image.new('RGB',(32,32),(100,40,50)).save(target)
        return target

    monkeypatch.setattr(FfmpegMediaProcessor,'extract_frame',extract)
    note=asyncio.run(services.generate_video_ai_summary.arun(series_id,video_id))
    assert '[[IMG:1]]' in note.content
    frame=workspace.materialize_artifact(video_id=video_id,kind='note_frame',filename='1.jpg')
    assert frame is not None
    with Image.open(frame) as image:
        assert image.size == (32,32)


def test_delete_does_not_deadlock_with_a_publisher_holding_the_job_lock(stored_video,mysql_sessions):
    workspace,series_id,video_id=stored_video
    repository=SqlJobRepository(mysql_sessions)
    submitted=repository.submit(workspace_id=workspace.workspace_id,resource_type='video',resource_id=video_id,
        operation='generate_summary',request_payload={'series_id':series_id},active_key='delete-race:'+video_id,
        idempotency_scope_id=None,idempotency_key=None)
    repository.claim(worker_id='publisher',lease_seconds=120,operations=frozenset({'generate_summary'}))
    locked,checking=Event(),Event()
    engine=mysql_sessions.kw['bind']

    def before_query(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith('SELECT id FROM jobs') and 'resource_id IN' in statement:
            checking.set()

    def publish():
        with mysql_sessions.begin() as session:
            session.scalar(select(Job).where(Job.id==submitted.id).with_for_update())
            locked.set()
            assert checking.wait(3)
            session.scalar(select(Video).where(Video.id==video_id).with_for_update())

    event.listen(engine,'before_cursor_execute',before_query)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            publishing=pool.submit(publish)
            assert locked.wait(3)
            deleting=pool.submit(workspace.delete_video,series_id,video_id)
            with pytest.raises(ActiveJobConflictError):
                deleting.result(timeout=5)
            publishing.result(timeout=5)
    finally:
        checking.set()
        event.remove(engine,'before_cursor_execute',before_query)
