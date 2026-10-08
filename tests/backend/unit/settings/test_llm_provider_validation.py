"""Reject unsupported protocols before saving settings or dispatching requests."""

import pytest

from backend.video_summary.infrastructure.config.settings import load_env_settings
from backend.video_summary.infrastructure.config.settings_service import SettingsService, SettingsValidationError


@pytest.mark.parametrize("provider", ["dashscope", "qwen", "minimax"])
def test_unsupported_saved_provider_is_not_silently_replaced(tmp_path, monkeypatch, provider):
    monkeypatch.setenv("OPENAI_PROVIDER", "openai")
    (tmp_path / ".env").write_text(f"OPENAI_PROVIDER={provider}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported llm provider"):
        load_env_settings(tmp_path)


@pytest.mark.parametrize("provider", ["dashscope", "qwen", "minimax"])
@pytest.mark.parametrize("operation", ["update_provider_settings", "test_provider_settings", "list_provider_models"])
def test_provider_operations_reject_unsupported_protocols(tmp_path, provider, operation):
    service = SettingsService(config_path=tmp_path / "settings.toml", root_dir=tmp_path,
                              faster_whisper_model_manager=None)
    arguments = dict(llm_provider=provider, openai_base_url="https://example.invalid/v1",
                     openai_api_key="test-key")
    if operation != "list_provider_models":
        arguments.update(openai_model="qwen-max", hf_endpoint=None)
    with pytest.raises(SettingsValidationError, match="unsupported llm provider"):
        getattr(service, operation)(**arguments)
    assert not (tmp_path / ".env").exists()
