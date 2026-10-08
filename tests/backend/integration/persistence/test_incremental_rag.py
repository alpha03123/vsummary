import lancedb
import pytest
from llama_index.core.embeddings import MockEmbedding
from pydantic import Field

from backend.video_summary.infrastructure.persistence.control_plane_repository import SqlControlPlaneRepository
from backend.video_summary.infrastructure.persistence.job_repository import SqlJobRepository
from backend.video_summary.infrastructure.persistence.sql_video_workspace import SqlVideoWorkspace
from backend.video_summary.infrastructure.rag.agent_memory.retrieval import SeriesRetrievalService, INDEX_TABLE_NAME


class RecordingEmbedding(MockEmbedding):
    texts: list[str] = Field(default_factory=list)

    def _get_text_embedding(self, text):
        self.texts.append(text)
        return super()._get_text_embedding(text)


def _rows(path):
    return lancedb.connect(str(path)).open_table(INDEX_TABLE_NAME).to_arrow().to_pylist()


def test_delta_reuses_other_vectors_and_keeps_previous_snapshot(stored_video, mysql_sessions, tmp_path):
    workspace, series_id, video_id = stored_video
    other = SqlControlPlaneRepository(mysql_sessions).create_video(series_id=series_id,title='BETA',source_kind='local')
    note=workspace.create_video_note(series_id,video_id,title='ALPHA',content='alpha original',source='manual')
    workspace.create_video_note(series_id,other,title='BETA',content='beta original',source='manual')
    embed=RecordingEmbedding(embed_dim=32)
    source=tmp_path/'source'
    SeriesRetrievalService(workspace=workspace,db_uri=str(source),embed_model=embed).refresh_all()
    original=_rows(source)
    workspace.update_video_note(series_id,video_id,note.id,title='ALPHA',content='alpha updated')
    embed.texts.clear()
    target=tmp_path/'target'
    service=SeriesRetrievalService(workspace=workspace,db_uri=str(target),embed_model=embed)
    change={'action':'upsert_video','series_id':series_id,'video_id':video_id}
    service.refresh_incremental(source,[change])
    assert embed.texts and all('BETA' not in text for text in embed.texts)
    assert _rows(source) == original
    current=_rows(target)
    assert any('alpha updated' in row['text'] for row in current)
    assert [row for row in current if row['metadata']['video_id']==other] == [
        row for row in original if row['metadata']['video_id']==other]
    embed.texts.clear()
    repeated=tmp_path/'repeated'
    SeriesRetrievalService(workspace=workspace,db_uri=str(repeated),embed_model=embed).refresh_incremental(target,[change])
    assert embed.texts == []
    assert len(_rows(repeated)) == len(current)
    workspace.save_video_ai_summary(series_id,video_id,title='AI note',content='fresh AI summary')
    ai_index=tmp_path/'ai-index'
    SeriesRetrievalService(workspace=workspace,db_uri=str(ai_index),embed_model=embed).refresh_incremental(repeated,[change])
    assert any('fresh AI summary' in row['text'] for row in _rows(ai_index))


def test_deleted_video_is_not_retrieved_before_index_refresh(stored_video, tmp_path):
    workspace, series_id, video_id=stored_video
    workspace.create_video_note(series_id,video_id,title='Private note',content='private material',source='manual')
    source=tmp_path/'source'
    embed=MockEmbedding(embed_dim=32)
    SeriesRetrievalService(workspace=workspace,db_uri=str(source),embed_model=embed).refresh_all()
    assert workspace.delete_video(series_id,video_id)
    service=SeriesRetrievalService(workspace=workspace,db_uri=str(source),embed_model=embed,
        schedule_refresh=lambda:None,index_location=lambda:source)
    result=service.search(scope_type='series',series_id=series_id,video_id='',query='private',
        target_source='notes',expand_context=False,context_window_seconds=0,max_hits=10)
    assert result['hits'] == []
    target=tmp_path/'target'
    SeriesRetrievalService(workspace=workspace,db_uri=str(target),embed_model=embed).refresh_incremental(source,[
        {'action':'delete_video','series_id':series_id,'video_id':video_id}])
    assert _rows(target) == []
    assert _rows(source)


def test_incremental_index_accepts_timed_transcript_after_text_only_notes(stored_video,tmp_path):
    workspace,series_id,video_id=stored_video
    workspace.create_video_note(series_id,video_id,title='Note',content='Untimed note',source='manual')
    embed=MockEmbedding(embed_dim=32)
    source=tmp_path/'source'
    SeriesRetrievalService(workspace=workspace,db_uri=str(source),embed_model=embed).refresh_all()
    workspace._publish_manual_content(series_id,video_id,{
        'transcript':{'language':'en','source_type':'generated','duration_ms':3000,
            'segments':[{'start_ms':0,'end_ms':3000,'text':'Timed transcript'}]},
        'summary':None,
    },'transcript_test')
    target=tmp_path/'target'
    SeriesRetrievalService(workspace=workspace,db_uri=str(target),embed_model=embed).refresh_incremental(source,[
        {'action':'upsert_video','series_id':series_id,'video_id':video_id}])
    assert any('Timed transcript' in row['text'] for row in _rows(target))


def test_refresh_acknowledges_only_snapshot_revisions(stored_video,mysql_sessions):
    workspace, series_id, video_id=stored_video
    repository=SqlJobRepository(mysql_sessions)
    repository.request_index_refresh(workspace.workspace_id)
    claim=repository.claim(worker_id='index',lease_seconds=120,operations=frozenset({'refresh_rag_index'}))
    first=repository.index_refresh_plan(workspace.workspace_id)
    repository.request_index_refresh(workspace.workspace_id,action='upsert_video',series_id=series_id,video_id=video_id)
    repository.complete_index_refresh(claim,first.revision,'first-generation')
    repository.succeed(claim,detail='indexed')
    second=repository.index_refresh_plan(workspace.workspace_id)
    assert [change['action'] for change in second.changes] == ['upsert_video']
    assert second.revision > first.revision
    resumed=repository.claim(worker_id='index',lease_seconds=120,operations=frozenset({'refresh_rag_index'}))
    assert resumed is not None
    repository.request_index_refresh(workspace.workspace_id,action='delete_video',series_id=series_id,video_id=video_id)
    repository.complete_index_refresh(resumed,second.revision,'second-generation')
    assert repository.index_refresh_plan(workspace.workspace_id).changes[0]['action'] == 'delete_video'


def test_rag_source_respects_ownership_and_removes_deleted_notes(stored_video,mysql_sessions,tmp_path):
    workspace,series_id,video_id=stored_video
    note=workspace.create_video_note(series_id,video_id,title='Private',content='private note',source='manual')
    first=workspace.get_rag_documents(series_id,video_id)
    assert first
    assert workspace.get_rag_documents(series_id,video_id) == first
    foreign_id=SqlControlPlaneRepository(mysql_sessions).create_workspace(owner_scope_id='other',title='Other')
    foreign=SqlVideoWorkspace(session_factory=mysql_sessions,blob_store=workspace._blobs,
        cache_root=tmp_path/'foreign',workspace_id=foreign_id)
    assert foreign.get_rag_documents(series_id,video_id) == []
    with pytest.raises(LookupError):
        SqlJobRepository(mysql_sessions).request_index_refresh(foreign_id,action='upsert_video',video_id=video_id)
    assert workspace.delete_video_note(series_id,video_id,note.id)
    assert workspace.get_rag_documents(series_id,video_id) == []
