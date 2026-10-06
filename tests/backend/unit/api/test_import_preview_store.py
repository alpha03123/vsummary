import pytest
from backend.core.context import WorkspaceContext
from backend.core.import_preview import ImportPreviewStore
from backend.video_summary.library.linked_models import LinkedSeries,LinkedVideo

def test_selection_is_explicit_owned_and_does_not_mutate_original_collection(tmp_path):
    owner=WorkspaceContext('workspace','owner','request')
    store=ImportPreviewStore(tmp_path,owner)
    videos=[LinkedVideo('BVtest',index,f'Episode {index}','',60,'https://www.bilibili.com/video/BVtest/') for index in (1,2)]
    linked=LinkedSeries('series','Collection','','https://www.bilibili.com',videos=videos)
    preview=store.create('linked',linked.title,[{'id':video.video_id,'title':video.title,'duration_seconds':60} for video in videos],linked=linked)
    with store.locked(preview['token']) as plan:
        selected=store.linked(plan,[videos[1].video_id])
        assert len(selected.videos)==1 and selected.videos[0].item_index==2
        assert len(plan['linked']['videos'])==2
        with pytest.raises(ValueError):store.selected(plan,[])
        with pytest.raises(ValueError):store.selected(plan,['unknown'])
    other=ImportPreviewStore(tmp_path,WorkspaceContext('workspace','other','request'))
    with pytest.raises(PermissionError):
        with other.locked(preview['token']):pass
    store.discard(preview['token'])
    assert not store.path(preview['token']).exists()

def test_expiration_removes_uncommitted_files(tmp_path,monkeypatch):
    source=tmp_path/'source.mp4';source.write_bytes(b'source')
    store=ImportPreviewStore(tmp_path/'previews',WorkspaceContext('workspace','owner','request'),ttl_seconds=1)
    preview=store.create('files','Pending',[{'id':'item','title':'Video','path':str(source),'duration_seconds':3}])
    monkeypatch.setattr('backend.core.import_preview.time.time',lambda:preview['expires_at']+1)
    ImportPreviewStore.expire(store.root)
    assert not store.path(preview['token']).exists()
