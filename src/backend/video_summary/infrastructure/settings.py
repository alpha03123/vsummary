from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


VALID_DEVICES = {"auto", "cpu", "gpu"}
VALID_ASR_PROVIDERS = {"faster_whisper"}
VALID_THEMES = {"light", "dark"}


@dataclass(frozen=True)
class FasterWhisperSettings:
    device: str
    model_size: str
    compute_type: str
    models_dir: Path


@dataclass(frozen=True)
class AsrSettings:
    provider: str
    language: str
    transcript_enhancement_enabled: bool
    faster_whisper: FasterWhisperSettings


@dataclass(frozen=True)
class OpenAISettings:
    base_url: str
    model: str


@dataclass(frozen=True)
class WorkspaceUiSettings:
    theme: str
    show_takeaways: bool
    ai_transcript_enhancement: bool


@dataclass(frozen=True)
class AppSettings:
    asr: AsrSettings
    openai: OpenAISettings
    workspace_ui: WorkspaceUiSettings


def load_settings(config_path: Path, root_dir: Path) -> AppSettings:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))

    asr_payload = payload["asr"]
    provider = asr_payload["provider"].lower()
    if provider not in VALID_ASR_PROVIDERS:
        raise ValueError(f"Unsupported asr.provider: {provider}")

    faster_payload = asr_payload["faster_whisper"]
    faster_device = faster_payload["device"].lower()
    if faster_device not in VALID_DEVICES:
        raise ValueError(f"Unsupported faster_whisper.device: {faster_device}")

    faster_settings = FasterWhisperSettings(
        device=faster_device,
        model_size=faster_payload["model_size"],
        compute_type=faster_payload["compute_type"],
        models_dir=root_dir / "data" / "models" / "faster-whisper",
    )

    asr_settings = AsrSettings(
        provider=provider,
        language=asr_payload.get("language", "zh"),
        transcript_enhancement_enabled=bool(asr_payload.get("transcript_enhancement_enabled", True)),
        faster_whisper=faster_settings,
    )

    openai_payload = payload["openai"]
    openai_settings = OpenAISettings(
        base_url=openai_payload["base_url"],
        model=openai_payload["model"],
    )

    workspace_ui_payload = payload.get("workspace_ui", {})
    workspace_ui_settings = WorkspaceUiSettings(
        theme=_normalize_theme(workspace_ui_payload.get("theme")),
        show_takeaways=bool(workspace_ui_payload.get("show_takeaways", True)),
        ai_transcript_enhancement=bool(workspace_ui_payload.get("ai_transcript_enhancement", True)),
    )

    return AppSettings(
        asr=asr_settings,
        openai=openai_settings,
        workspace_ui=workspace_ui_settings,
    )


def save_settings(config_path: Path, settings: AppSettings) -> None:
    config_path.write_text(_render_settings_toml(settings), encoding="utf-8")


def replace_workspace_ui_settings(settings: AppSettings, workspace_ui: WorkspaceUiSettings) -> AppSettings:
    return AppSettings(
        asr=settings.asr,
        openai=settings.openai,
        workspace_ui=workspace_ui,
    )


def replace_faster_whisper_model_size(settings: AppSettings, model_size: str) -> AppSettings:
    return AppSettings(
        asr=AsrSettings(
            provider=settings.asr.provider,
            language=settings.asr.language,
            transcript_enhancement_enabled=settings.asr.transcript_enhancement_enabled,
            faster_whisper=FasterWhisperSettings(
                device=settings.asr.faster_whisper.device,
                model_size=model_size,
                compute_type=settings.asr.faster_whisper.compute_type,
                models_dir=settings.asr.faster_whisper.models_dir,
            ),
        ),
        openai=settings.openai,
        workspace_ui=settings.workspace_ui,
    )


def _resolve(root_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return root_dir / path


def _normalize_theme(value: object) -> str:
    if isinstance(value, str) and value in VALID_THEMES:
        return value
    return "light"


def _render_settings_toml(settings: AppSettings) -> str:
    lines = [
        "[asr]",
        f'provider = "{settings.asr.provider}"',
        f'language = "{settings.asr.language}"',
        f"transcript_enhancement_enabled = {_toml_bool(settings.asr.transcript_enhancement_enabled)}",
        "",
        "[asr.faster_whisper]",
        f'device = "{settings.asr.faster_whisper.device}"',
        f'model_size = "{settings.asr.faster_whisper.model_size}"',
        f'compute_type = "{settings.asr.faster_whisper.compute_type}"',
        "",
        "[openai]",
        f'base_url = "{settings.openai.base_url}"',
        f'model = "{settings.openai.model}"',
        "",
        "[workspace_ui]",
        f'theme = "{settings.workspace_ui.theme}"',
        f"show_takeaways = {_toml_bool(settings.workspace_ui.show_takeaways)}",
        f"ai_transcript_enhancement = {_toml_bool(settings.workspace_ui.ai_transcript_enhancement)}",
        "",
    ]
    return "\n".join(lines)


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_path(path: Path) -> str:
    return str(path).replace("\\", "/")
