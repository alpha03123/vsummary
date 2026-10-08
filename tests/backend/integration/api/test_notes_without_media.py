from fastapi.testclient import TestClient

from backend.local.http.app import create_app
from backend.video_summary.library.usecases import GetVideoNotes, CreateVideoNote, UpdateVideoNote, DeleteVideoNote, GetVideoSource
from tests._api_fixtures import make_api_container, make_workspace_services


def test_note_crud_without_source_media(stored_video):
    workspace, series_id, video_id = stored_video
    workspace.get_video_source(series_id,video_id).source_path.unlink()
    assert workspace.get_video_source(series_id,video_id) is None
    services = make_workspace_services(workspace_id=workspace.workspace_id,
        get_video_source=GetVideoSource(workspace), get_video_notes=GetVideoNotes(workspace),
        create_video_note=CreateVideoNote(workspace), update_video_note=UpdateVideoNote(workspace),
        delete_video_note=DeleteVideoNote(workspace))
    client = TestClient(create_app(make_api_container(services=services)))
    url = f"/api/videos/{series_id}/{video_id}/notes"
    created = client.post(url,json={"title":"Note","content":"Original","source":"manual"})
    assert created.status_code == 200
    note_id = created.json()["id"]
    updated = client.put(f"{url}/{note_id}",json={"title":"Updated","content":"New content"})
    assert updated.status_code == 200
    assert updated.json()["content"] == "New content"
    assert client.get(url).json()["notes"][0]["content"] == "New content"
    assert client.delete(f"{url}/{note_id}").status_code == 200
    assert client.get(url).json()["notes"] == []
    assert client.put(f"{url}/{note_id}",json={"title":"Missing","content":"Cannot revive"}).status_code == 404
