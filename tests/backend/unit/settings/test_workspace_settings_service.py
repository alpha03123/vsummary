from __future__ import annotations

import sys
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _path_setup  # noqa: F401

from backend.video_summary.infrastructure.config.settings_service import SettingsService, SettingsValidationError
from backend.video_summary.infrastructure.config.settings import (
    EnvSettings,
    apply_runtime_env_overrides,
    load_env_settings,
    load_settings,
    save_env_settings,
)


class WorkspaceSettingsServiceTests(unittest.TestCase):
    def test_runtime_env_overrides_keep_existing_env_when_dotenv_value_is_empty(self) -> None:
        """`.env` 里的空值表示"本文件不表态"，不得覆盖 shell 里已设好的值。

        这条语义很关键：`start.bat` / `build_release.ps1` 会先把 `HF_ENDPOINT`
        `HF_HOME` `HUGGINGFACE_HUB_CACHE` 指到项目内目录，随后才加载 `.env`。
        旧行为会 `pop` 掉这些变量，导致镜像失效、缓存跑回用户主目录。
        """
        import huggingface_hub.constants as hf_constants

        previous = os.environ.get("HF_ENDPOINT")
        previous_endpoint = hf_constants.ENDPOINT
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root_dir = Path(temp_dir)
                (root_dir / ".env").write_text("HF_ENDPOINT=\n", encoding="utf-8")
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                hf_constants.ENDPOINT = ""

                apply_runtime_env_overrides(root_dir)

                self.assertEqual(os.environ.get("HF_ENDPOINT"), "https://hf-mirror.com")
                self.assertEqual(hf_constants.ENDPOINT, "https://hf-mirror.com")
        finally:
            if previous is None:
                os.environ.pop("HF_ENDPOINT", None)
            else:
                os.environ["HF_ENDPOINT"] = previous
            hf_constants.ENDPOINT = previous_endpoint

    def test_load_env_settings_does_not_seed_blank_hf_endpoint(self) -> None:
        previous = os.environ.get("HF_ENDPOINT")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root_dir = Path(temp_dir)
                (root_dir / ".env").write_text("HF_ENDPOINT=\nOPENAI_MODEL=test\n", encoding="utf-8")
                os.environ.pop("HF_ENDPOINT", None)

                settings = load_env_settings(root_dir)

                self.assertEqual(settings.hf_endpoint, "")
                self.assertNotIn("HF_ENDPOINT", os.environ)
        finally:
            if previous is None:
                os.environ.pop("HF_ENDPOINT", None)
            else:
                os.environ["HF_ENDPOINT"] = previous

    def test_runtime_env_overrides_updates_loaded_huggingface_hub_endpoint(self) -> None:
        import huggingface_hub.constants as hf_constants

        previous_env = os.environ.get("HF_ENDPOINT")
        previous_endpoint = hf_constants.ENDPOINT
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root_dir = Path(temp_dir)
                (root_dir / ".env").write_text("HF_ENDPOINT=https://hf-mirror.com\n", encoding="utf-8")
                os.environ.pop("HF_ENDPOINT", None)
                hf_constants.ENDPOINT = "https://huggingface.co"

                apply_runtime_env_overrides(root_dir)

                self.assertEqual(os.environ["HF_ENDPOINT"], "https://hf-mirror.com")
                self.assertEqual(hf_constants.ENDPOINT, "https://hf-mirror.com")
        finally:
            if previous_env is None:
                os.environ.pop("HF_ENDPOINT", None)
            else:
                os.environ["HF_ENDPOINT"] = previous_env
            hf_constants.ENDPOINT = previous_endpoint

    def test_get_and_update_workspace_settings_include_window_tokens_video_concurrency_rag_and_web_search_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text(
                "\n".join(
                    [
                        "OPENAI_PROVIDER=openai",
                        "OPENAI_BASE_URL=https://example.com/v1",
                        "OPENAI_MODEL=test-model",
                        "OPENAI_API_KEY=test-key",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")

            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
                rag_model_manager=FakeRagModelManager(downloaded={"reranker"}),
            )

            current = service.get_workspace_settings()
            self.assertEqual(current.window_tokens, 1_000_000)
            self.assertEqual(current.answer_detail_level, "medium")
            self.assertEqual(current.reasoning_effort, "none")
            self.assertEqual(current.video_generation_concurrency, 1)
            self.assertEqual(current.rag_max_hits, 5)
            self.assertTrue(current.rag_rerank_enabled)
            self.assertFalse(current.web_search_enabled)

            updated = service.update_workspace_settings(
                theme="dark",
                show_takeaways=False,
                layout_mode="chat_center",
                transcript_enhancement_enabled=False,
                asr_model_quality="large-v3-turbo",
                transcription_mode="accurate",
                rag_embedding_device="cpu",
                rag_max_hits=7,
                rag_rerank_enabled=False,
                window_tokens=222_222,
                answer_detail_level="long",
                reasoning_effort="high",
                video_generation_concurrency=5,
                web_search_enabled=True,
            )

            self.assertEqual(updated.window_tokens, 222_222)
            self.assertEqual(updated.layout_mode, "chat_center")
            self.assertEqual(updated.answer_detail_level, "long")
            self.assertEqual(updated.reasoning_effort, "high")
            self.assertEqual(updated.video_generation_concurrency, 5)
            self.assertEqual(updated.rag_max_hits, 7)
            self.assertFalse(updated.rag_rerank_enabled)
            self.assertTrue(updated.web_search_enabled)
            rendered = config_path.read_text(encoding="utf-8")
            self.assertIn("[agent_context]", rendered)
            self.assertIn("window_tokens = 222222", rendered)
            self.assertIn('answer_detail_level = "long"', rendered)
            self.assertIn('reasoning_effort = "high"', rendered)
            self.assertIn("[agent_context.advanced]", rendered)
            self.assertIn("direct_summary_threshold_ratio = 0.9", rendered)
            self.assertIn("[generation]", rendered)
            self.assertIn("video_generation_concurrency = 5", rendered)
            self.assertIn("summary_chunk_concurrency = 1", rendered)
            self.assertIn("[agent_retrieval]", rendered)
            self.assertIn("max_hits = 7", rendered)
            self.assertIn("rerank_enabled = false", rendered)
            self.assertIn("[web_search]", rendered)
            self.assertIn("enabled = true", rendered)
            self.assertIn('provider = "litellm"', rendered)
            self.assertIn('layout_mode = "chat_center"', rendered)
            self.assertNotIn("series_video_concurrency", rendered)

    def test_update_workspace_settings_rejects_rerank_enabled_when_reranker_model_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")

            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
                rag_model_manager=FakeRagModelManager(downloaded=set()),
            )

            with self.assertRaisesRegex(SettingsValidationError, "重排序模型尚未下载"):
                service.update_workspace_settings(
                    theme="light",
                    show_takeaways=True,
                    layout_mode="video_center",
                    transcript_enhancement_enabled=True,
                    asr_model_quality="large-v3-turbo",
                    transcription_mode="accurate",
                    rag_embedding_device="cpu",
                    rag_max_hits=5,
                    rag_rerank_enabled=True,
                    window_tokens=1_000_000,
                    answer_detail_level="medium",
                    reasoning_effort="medium",
                    video_generation_concurrency=1,
                    web_search_enabled=False,
                )

    def test_update_workspace_settings_rejects_invalid_answer_detail_level(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")

            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
                rag_model_manager=FakeRagModelManager(downloaded={"reranker"}),
            )

            with self.assertRaisesRegex(SettingsValidationError, "answer_detail_level"):
                service.update_workspace_settings(
                    theme="light",
                    show_takeaways=True,
                    layout_mode="video_center",
                    transcript_enhancement_enabled=True,
                    asr_model_quality="large-v3-turbo",
                    transcription_mode="accurate",
                    rag_embedding_device="cpu",
                    rag_max_hits=5,
                    rag_rerank_enabled=True,
                    window_tokens=1_000_000,
                    answer_detail_level="verbose",
                    reasoning_effort="medium",
                    video_generation_concurrency=1,
                    web_search_enabled=False,
                )

    def test_update_workspace_settings_rejects_invalid_reasoning_effort(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")

            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
                rag_model_manager=FakeRagModelManager(downloaded={"reranker"}),
            )

        with self.assertRaisesRegex(SettingsValidationError, "reasoning_effort"):
            service.update_workspace_settings(
                    theme="light",
                    show_takeaways=True,
                    layout_mode="video_center",
                    transcript_enhancement_enabled=True,
                    asr_model_quality="large-v3-turbo",
                    transcription_mode="accurate",
                    rag_embedding_device="cpu",
                    rag_max_hits=5,
                    rag_rerank_enabled=True,
                    window_tokens=1_000_000,
                    answer_detail_level="medium",
                    reasoning_effort="minimal",
                    video_generation_concurrency=1,
                    web_search_enabled=False,
                )

    def test_get_workspace_settings_reports_rerank_disabled_when_reranker_model_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")

            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
                rag_model_manager=FakeRagModelManager(downloaded=set()),
            )

            self.assertFalse(service.get_workspace_settings().rag_rerank_enabled)

    def test_load_settings_reads_generation_concurrency_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(
                _sample_settings_toml()
                + "\n\n[generation]\nvideo_generation_concurrency = 2\nsummary_chunk_concurrency = 4\n",
                encoding="utf-8",
            )

            settings = load_settings(config_path, root_dir)

            self.assertEqual(settings.generation.video_generation_concurrency, 2)
            self.assertEqual(settings.generation.summary_chunk_concurrency, 4)

    def test_load_settings_uses_generation_concurrency_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")

            settings = load_settings(config_path, root_dir)

            self.assertEqual(settings.generation.video_generation_concurrency, 1)
            self.assertEqual(settings.generation.summary_chunk_concurrency, 1)

    def test_load_settings_uses_web_search_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")

            settings = load_settings(config_path, root_dir)

            self.assertFalse(settings.web_search.enabled)
            self.assertEqual(settings.web_search.provider, "litellm")
            self.assertEqual(settings.web_search.mode, "native")
            self.assertEqual(settings.web_search.search_context_size, "medium")
            self.assertEqual(settings.web_search.max_results, 5)
            self.assertEqual(settings.web_search.timeout_seconds, 10)

    def test_load_settings_uses_auto_language_and_empty_prompt_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml().replace('language = "auto"\n', ""), encoding="utf-8")

            settings = load_settings(config_path, root_dir)

            self.assertEqual(settings.asr.language, "auto")
            self.assertEqual(settings.asr.faster_whisper.initial_prompt, "")

    def test_load_settings_creates_local_settings_from_example_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            example_path = root_dir / "config" / "settings.toml.example"
            example_path.write_text(_sample_settings_toml(), encoding="utf-8")

            settings = load_settings(config_path, root_dir)

            self.assertTrue(config_path.exists())
            self.assertEqual(config_path.read_text(encoding="utf-8"), _sample_settings_toml())
            self.assertEqual(settings.workspace_ui.layout_mode, "video_center")

    def test_load_settings_rejects_generation_concurrency_smaller_than_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(
                _sample_settings_toml()
                + "\n\n[generation]\nvideo_generation_concurrency = 0\nsummary_chunk_concurrency = 1\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "video_generation_concurrency"):
                load_settings(config_path, root_dir)

    def test_load_settings_rejects_rag_max_hits_smaller_than_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(
                _sample_settings_toml().replace("max_hits = 5", "max_hits = 0"),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "agent_retrieval.max_hits"):
                load_settings(config_path, root_dir)

    def test_provider_settings_save_and_load_preserve_base_url_without_v1_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)

            save_env_settings(
                root_dir,
                EnvSettings(
                    provider="openai",
                    base_url="https://jiuuij.de5.net",
                    model="test-model",
                    api_key="test-key",
                ),
            )

            rendered = (root_dir / ".env").read_text(encoding="utf-8")
            self.assertIn("OPENAI_BASE_URL=https://jiuuij.de5.net\n", rendered)
            self.assertNotIn("OPENAI_BASE_URL=https://jiuuij.de5.net/v1", rendered)
            self.assertEqual(load_env_settings(root_dir).base_url, "https://jiuuij.de5.net")

    def test_provider_settings_test_reports_model_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("OPENAI_API_KEY=saved-key\n", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")
            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
            )

            with patch("backend.video_summary.infrastructure.config.settings_service.LiteLLMCompletionGateway", TimeoutGateway):
                with self.assertRaisesRegex(RuntimeError, "^模型超时$"):
                    service.test_provider_settings(
                        llm_provider="openai",
                        openai_base_url="https://jiuuij.de5.net",
                        openai_model="test-model",
                        openai_api_key=None,
                        hf_endpoint=None,
                    )

    def test_list_provider_models_uses_litellm_provider_endpoint_without_writing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("OPENAI_API_KEY=saved-key\n", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")
            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
            )

            with patch(
                "litellm.get_valid_models",
                return_value=["gpt-5.4-mini", "gpt-5.4", "gpt-5.4"],
            ) as get_valid_models:
                models = service.list_provider_models(
                    llm_provider="openai",
                    openai_base_url="https://api.example.com/v1",
                    openai_api_key=None,
                )
            rendered_env = (root_dir / ".env").read_text(encoding="utf-8")

        self.assertEqual(models, ["gpt-5.4", "gpt-5.4-mini"])
        self.assertIn("OPENAI_API_KEY=saved-key", rendered_env)
        self.assertEqual(get_valid_models.call_args.kwargs["litellm_params"].api_base, "https://api.example.com")

    def test_asr_settings_test_uses_dashscope_upload_certificate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("DASHSCOPE_API_KEY=saved-dashscope-key\n", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")
            calls: list[tuple[str, str, str]] = []

            class OssUtils:
                @classmethod
                def get_upload_certificate(cls, *, model, api_key, base_address):
                    calls.append((model, api_key, base_address))
                    return types.SimpleNamespace(status_code=200, code="", message="")

            dashscope_module = types.ModuleType("dashscope")
            utils_module = types.ModuleType("dashscope.utils")
            oss_utils_module = types.ModuleType("dashscope.utils.oss_utils")
            oss_utils_module.OssUtils = OssUtils
            with patch.dict(
                sys.modules,
                {
                    "dashscope": dashscope_module,
                    "dashscope.utils": utils_module,
                    "dashscope.utils.oss_utils": oss_utils_module,
                },
            ):
                service = SettingsService(
                    config_path=config_path,
                    root_dir=root_dir,
                    faster_whisper_model_manager=FakeFasterWhisperModelManager(),
                )

                message = service.test_asr_settings(
                    asr_provider="aliyun_bailian",
                    asr_cloud_model="paraformer-v2",
                    asr_base_url="https://dashscope.aliyuncs.com",
                    asr_api_key=None,
                )

            self.assertEqual(message, "阿里云百炼 ASR 连接正常。")
            self.assertEqual(
                calls,
                [("paraformer-v2", "saved-dashscope-key", "https://dashscope.aliyuncs.com/api/v1")],
            )

    def test_asr_settings_test_requires_dashscope_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            (root_dir / "config").mkdir(parents=True, exist_ok=True)
            (root_dir / ".env").write_text("", encoding="utf-8")
            config_path = root_dir / "config" / "settings.toml"
            config_path.write_text(_sample_settings_toml(), encoding="utf-8")
            service = SettingsService(
                config_path=config_path,
                root_dir=root_dir,
                faster_whisper_model_manager=FakeFasterWhisperModelManager(),
            )

            with self.assertRaisesRegex(SettingsValidationError, "ASR API Key"):
                service.test_asr_settings(
                    asr_provider="aliyun_bailian",
                    asr_cloud_model="paraformer-v2",
                    asr_base_url="https://dashscope.aliyuncs.com",
                    asr_api_key=None,
                )


class FakeFasterWhisperModelManager:
    def is_supported(self, model_id: str) -> bool:
        return model_id == "large-v3-turbo"


class FakeRagModelManager:
    def __init__(self, *, downloaded: set[str]) -> None:
        self._downloaded = downloaded

    def is_downloaded(self, key: str) -> bool:
        return key in self._downloaded


class TimeoutGateway:
    def __init__(self, **kwargs) -> None:
        del kwargs

    def test_connection(self) -> str:
        raise TimeoutError("request timed out")


def _sample_settings_toml() -> str:
    return """
[asr]
provider = "faster_whisper"
language = "auto"
transcript_enhancement_enabled = true

[asr.faster_whisper]
device = "gpu"
model_size = "large-v3-turbo"
compute_type = "float16"
transcription_mode = "accurate"

[workspace_ui]
theme = "light"
show_takeaways = true
layout_mode = "video_center"

[debug]
mode = false

[agent_context]
window_tokens = 1000000

[agent_context.advanced]
reserved_output_tokens = 20000
warning_threshold_ratio = 0.6
compact_threshold_ratio = 0.8
blocking_threshold_ratio = 0.92
keep_tail_messages = 6
projection_max_tokens_ratio = 0.08
planner_transport = "structured"
direct_summary_threshold_ratio = 0.9

[agent_retrieval]
embedding_provider = "fastembed"
embedding_model = "BAAI/bge-small-zh-v1.5"
embedding_device = "cpu"
embedding_batch_size = 8
max_hits = 5
rerank_enabled = true
""".strip()


if __name__ == "__main__":
    unittest.main()
