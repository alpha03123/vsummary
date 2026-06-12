from __future__ import annotations

from pathlib import Path
from threading import Lock

from backend.video_summary.adapters.llm.knowledge_card_generator import LiteLLMKnowledgeCardGenerator
from backend.video_summary.composition.video_summary_runtime import build_litellm_completion_gateway
from backend.video_summary.configuration.settings import load_settings
from backend.video_summary.summary_generation.service_ports import KnowledgeCardResult


class ConfiguredKnowledgeCardGenerator:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._config_path = root_dir / "config" / "settings.toml"
        self._dotenv_path = root_dir / ".env"
        self._generator_lock = Lock()
        self._cached_signature: tuple[str, str] | None = None
        self._cached_generator: LiteLLMKnowledgeCardGenerator | None = None

    def run(self, *, title: str, summary_data: dict[str, object]) -> list[KnowledgeCardResult]:
        return self._get_generator().run(title=title, summary_data=summary_data)

    def _get_generator(self) -> LiteLLMKnowledgeCardGenerator:
        signature = (
            self._config_path.read_text(encoding="utf-8"),
            self._dotenv_path.read_text(encoding="utf-8") if self._dotenv_path.exists() else "",
        )
        with self._generator_lock:
            if self._cached_generator is None or self._cached_signature != signature:
                settings = load_settings(config_path=self._config_path, root_dir=self._root_dir)
                gateway = build_litellm_completion_gateway(settings)
                self._cached_generator = LiteLLMKnowledgeCardGenerator(gateway)
                self._cached_signature = signature
            return self._cached_generator
