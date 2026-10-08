import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.http.static_assets import mount_frontend_dist


@pytest.mark.parametrize("path", [
    "/%2e%2e/%2e%2e/private.txt",
    "/..%2f..%2fprivate.txt",
    "/..%5c..%5cprivate.txt",
    "/C%3A%5cprivate.txt",
    "/%5c%5cinvalid-host%5cshare%5cprivate.txt",
])
def test_frontend_routes_reject_paths_outside_dist(tmp_path, path):
    dist=tmp_path/'src/frontend/dist'
    dist.mkdir(parents=True)
    (dist/'index.html').write_text('App',encoding='utf-8')
    (tmp_path/'src/private.txt').write_text('private fixture',encoding='utf-8')
    app=FastAPI()
    mount_frontend_dist(app,tmp_path)
    with TestClient(app) as client:
        response=client.get(path)
        assert response.status_code == 404
        assert 'private fixture' not in response.text
        assert client.get('/workspace/video').text == 'App'
