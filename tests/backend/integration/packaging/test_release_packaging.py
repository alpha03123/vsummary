from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests import _path_setup
from backend.api.http.app import create_app
from backend.api.adapters.agent_runtime_provider import _resolve_local_reranker_cache_dir
from tools.release_packaging import (
    PACKAGE_VARIANTS,
    build_release_layout,
    render_start_bat,
)


class FrontendStaticMountTests(unittest.TestCase):
    def test_create_app_serves_frontend_dist_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            dist_dir = root_dir / "src" / "frontend" / "dist"
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text("<html><body>frontend</body></html>", encoding="utf-8")
            (assets_dir / "app.js").write_text("console.log('ok');", encoding="utf-8")

            app = create_app(container=DummyContainer(root_dir))

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
                app = create_app(container=DummyContainer(root_dir))

                with TestClient(app) as client:
                    asset_response = client.get("/assets/app.js")

            self.assertEqual(asset_response.status_code, 200)
            self.assertIn(
                asset_response.headers["content-type"].split(";")[0],
                {"application/javascript", "text/javascript"},
            )


class DummyContainer:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir


class ReleasePackagingSpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = _path_setup.REPO_ROOT

    def test_package_variants_define_distinct_env_and_settings_templates(self) -> None:
        cpu = PACKAGE_VARIANTS["cpu"]
        gpu = PACKAGE_VARIANTS["gpu"]

        self.assertNotEqual(cpu.environment_file, gpu.environment_file)
        self.assertNotEqual(cpu.settings_template, gpu.settings_template)
        self.assertTrue((self.repo_root / cpu.environment_file).is_file())
        self.assertTrue((self.repo_root / gpu.environment_file).is_file())
        self.assertTrue((self.repo_root / cpu.settings_template).is_file())
        self.assertTrue((self.repo_root / gpu.settings_template).is_file())

    def test_package_variants_do_not_bundle_models(self) -> None:
        cpu = PACKAGE_VARIANTS["cpu"]
        gpu = PACKAGE_VARIANTS["gpu"]

        self.assertFalse(hasattr(cpu, "huggingface_models"))
        self.assertFalse(hasattr(gpu, "huggingface_models"))

    def test_cpu_settings_template_uses_local_embedding_model_path(self) -> None:
        cpu = PACKAGE_VARIANTS["cpu"]
        rendered = (self.repo_root / cpu.settings_template).read_text(encoding="utf-8")

        self.assertIn('embedding_provider = "fastembed"', rendered)
        self.assertIn('embedding_model = "BAAI/bge-small-zh-v1.5"', rendered)

    def test_build_release_layout_targets_external_pack_root(self) -> None:
        layout = build_release_layout(
            repo_root=self.repo_root,
            pack_root=Path(r"E:\gittools\self\selftest\packs"),
            kind="cpu",
        )

        self.assertEqual(layout.package_root, Path(r"E:\gittools\self\selftest\packs\vsummary-cpu"))
        self.assertEqual(layout.build_root, Path(r"E:\gittools\self\selftest\packs\_build\cpu"))
        self.assertEqual(layout.runtime_root, Path(r"E:\gittools\self\selftest\packs\_build\cpu\runtime"))

    def test_render_start_bat_sets_local_hf_cache_and_backend_paths(self) -> None:
        script = render_start_bat()

        self.assertIn("HF_HOME", script)
        self.assertIn("HUGGINGFACE_HUB_CACHE", script)
        self.assertIn("-m backend.api.http.server", script)
        self.assertIn("PYTHONPATH=%ROOT%\\src", script)

    def test_resolve_local_reranker_cache_dir_prefers_packaged_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            local_dir = root_dir / "data" / "models" / "fastembed" / "models--BAAI--bge-reranker-base"
            local_dir.mkdir(parents=True, exist_ok=True)

            cache_dir = _resolve_local_reranker_cache_dir(root_dir)

            self.assertEqual(cache_dir, str(root_dir / "data" / "models" / "fastembed"))


if __name__ == "__main__":
    unittest.main()
