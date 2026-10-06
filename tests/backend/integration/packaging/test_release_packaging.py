from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests import _path_setup
from tests._api_fixtures import make_api_container
from backend.local.http.app import create_app
from backend.api.adapters.agent_runtime_provider import _resolve_local_reranker_cache_dir
from tools.release_packaging import (
    ReleaseArtifact,
    build_release_manifest,
)


class FrontendStaticMountTests(unittest.TestCase):
    def test_isolated_runtime_serves_assets_from_the_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            installation = directory / "installation"
            runtime = directory / "runtime"
            assets = installation / "src/frontend/dist/assets"
            assets.mkdir(parents=True)
            (assets.parent / "index.html").write_text("<script type='module' src='/assets/app.js'></script>", encoding="utf-8")
            script = b"export const runtime = 'installation';"
            (assets / "app.js").write_bytes(script)
            runtime.mkdir()
            config = runtime / ".env"
            config.write_bytes(b"OPENAI_API_KEY=test-runtime-key\n")
            application = create_app(container=make_api_container(root_dir=runtime), frontend_root=installation)

            with TestClient(application) as client:
                index = client.get("/")
                asset = client.get("/assets/app.js")

            self.assertEqual(index.status_code, 200)
            self.assertEqual(asset.status_code, 200)
            self.assertEqual(asset.content, script)
            self.assertEqual(config.read_bytes(), b"OPENAI_API_KEY=test-runtime-key\n")

    def test_create_app_serves_frontend_dist_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            dist_dir = root_dir / "src" / "frontend" / "dist"
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text("<html><body>frontend</body></html>", encoding="utf-8")
            (assets_dir / "app.js").write_text("console.log('ok');", encoding="utf-8")

            app = create_app(container=make_api_container(root_dir=root_dir))

            with TestClient(app) as client:
                index_response = client.get("/")
                asset_response = client.get("/assets/app.js")
                deep_link_response = client.get("/workspace/video-1")

            self.assertEqual(index_response.status_code, 200)
            self.assertIn("frontend", index_response.text)
            self.assertEqual(asset_response.status_code, 200)
            self.assertIn("console.log", asset_response.text)
            self.assertEqual(deep_link_response.status_code, 200)
            self.assertIn("frontend", deep_link_response.text)

    def test_frontend_js_assets_are_served_with_javascript_content_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            dist_dir = root_dir / "src" / "frontend" / "dist"
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text(
                '<script type="module" src="/assets/app.js"></script>',
                encoding="utf-8",
            )
            (assets_dir / "app.js").write_text("console.log('ok');", encoding="utf-8")

            with patch("starlette.responses.guess_type", return_value=("text/plain", None)):
                app = create_app(container=make_api_container(root_dir=root_dir))

                with TestClient(app) as client:
                    asset_response = client.get("/assets/app.js")

            self.assertEqual(asset_response.status_code, 200)
            self.assertIn(
                asset_response.headers["content-type"].split(";")[0],
                {"application/javascript", "text/javascript"},
            )


class ReleasePackagingSpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = _path_setup.REPO_ROOT

    def test_resolve_local_reranker_cache_dir_prefers_packaged_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            local_dir = root_dir / "data" / "models" / "fastembed" / "models--BAAI--bge-reranker-base"
            local_dir.mkdir(parents=True, exist_ok=True)

            cache_dir = _resolve_local_reranker_cache_dir(root_dir)

            self.assertEqual(cache_dir, str(root_dir / "data" / "models" / "fastembed"))

    def test_build_release_manifest_describes_full_and_delta_assets(self) -> None:
        manifest = build_release_manifest(
            version="v0.3.1",
            assets=[
                ReleaseArtifact(
                    name="vsummary-full-cpu-v0.3.1.7z",
                    role="full",
                    variant="cpu",
                    url="https://example.test/vsummary-full-cpu-v0.3.1.7z",
                    sha256="c" * 64,
                    size=789,
                ),
                ReleaseArtifact(
                    name="vsummary-delta-cpu-v0.3.0-to-v0.3.1.zip",
                    role="delta",
                    variant="cpu",
                    from_version="v0.3.0",
                    to_version="v0.3.1",
                    url="https://example.test/vsummary-delta-cpu-v0.3.0-to-v0.3.1.zip",
                    sha256="d" * 64,
                    size=456,
                ),
            ],
        )

        self.assertEqual(manifest["version"], "v0.3.1")
        self.assertEqual(manifest["app"]["version"], "v0.3.1")
        self.assertEqual(manifest["runtime"], {})
        self.assertEqual(manifest["full"]["cpu"]["sha256"], "c" * 64)
        self.assertEqual(manifest["deltas"]["cpu"]["v0.3.0"]["to"], "v0.3.1")


if __name__ == "__main__":
    unittest.main()
