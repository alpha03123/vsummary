from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


VALID_DEVICES = {"auto", "cpu", "gpu"}
VALID_ASR_PROVIDERS = {"faster_whisper"}
VALID_THEMES = {"light", "dark"}
VALID_TRANSCRIPTION_MODES = {"fast", "balanced", "accurate"}


@dataclass(frozen=True)
class FasterWhisperSettings:
    device: str
    model_size: str
    compute_type: str
    transcription_mode: str
    models_dir: Path


@dataclass(frozen=True)
class AsrSettings:
    provider: str
    language: str
    transcript_enhancement_enabled: bool
    faster_whisper: FasterWhisperSettings


@dataclass(frozen=True)
class OpenAISettings:
    provider: str
    base_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class WorkspaceUiSettings:
    theme: str
    show_takeaways: bool


@dataclass(frozen=True)
class DebugSettings:
    mode: bool


@dataclass(frozen=True)
class AppSettings:
    asr: AsrSettings
    openai: OpenAISettings
    workspace_ui: WorkspaceUiSettings
    debug: DebugSettings


def load_settings(config_path: Path, root_dir: Path) -> AppSettings:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    env_values = load_env_settings(root_dir)

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
        transcription_mode=_normalize_transcription_mode(faster_payload.get("transcription_mode")),
        models_dir=root_dir / "data" / "models" / "faster-whisper",
    )

    asr_settings = AsrSettings(
        provider=provider,
        language=asr_payload.get("language", "zh"),
        transcript_enhancement_enabled=bool(asr_payload.get("transcript_enhancement_enabled", True)),
        faster_whisper=faster_settings,
    )

    openai_settings = OpenAISettings(
        provider=env_values.provider,
        base_url=normalize_openai_base_url(env_values.base_url),
        model=env_values.model,
        api_key=env_values.api_key,
    )

    workspace_ui_payload = payload.get("workspace_ui", {})
    workspace_ui_settings = WorkspaceUiSettings(
        theme=_normalize_theme(workspace_ui_payload.get("theme")),
        show_takeaways=bool(workspace_ui_payload.get("show_takeaways", True)),
    )
    debug_payload = payload.get("debug", {})
    debug_settings = DebugSettings(
        mode=bool(debug_payload.get("mode", False)),
    )

    return AppSettings(
        asr=asr_settings,
        openai=openai_settings,
        workspace_ui=workspace_ui_settings,
        debug=debug_settings,
    )


def save_settings(config_path: Path, settings: AppSettings) -> None:
    config_path.write_text(_render_settings_toml(settings), encoding="utf-8")


def replace_workspace_ui_settings(settings: AppSettings, workspace_ui: WorkspaceUiSettings) -> AppSettings:
    return AppSettings(
        asr=settings.asr,
        openai=settings.openai,
        workspace_ui=workspace_ui,
        debug=settings.debug,
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
                transcription_mode=settings.asr.faster_whisper.transcription_mode,
                models_dir=settings.asr.faster_whisper.models_dir,
            ),
        ),
        openai=settings.openai,
        workspace_ui=settings.workspace_ui,
        debug=settings.debug,
    )


def replace_transcript_enhancement_enabled(settings: AppSettings, transcript_enhancement_enabled: bool) -> AppSettings:
    return AppSettings(
        asr=AsrSettings(
            provider=settings.asr.provider,
            language=settings.asr.language,
            transcript_enhancement_enabled=transcript_enhancement_enabled,
            faster_whisper=settings.asr.faster_whisper,
        ),
        openai=settings.openai,
        workspace_ui=settings.workspace_ui,
        debug=settings.debug,
    )


def replace_faster_whisper_transcription_mode(settings: AppSettings, transcription_mode: str) -> AppSettings:
    normalized_mode = _normalize_transcription_mode(transcription_mode)
    return AppSettings(
        asr=AsrSettings(
            provider=settings.asr.provider,
            language=settings.asr.language,
            transcript_enhancement_enabled=settings.asr.transcript_enhancement_enabled,
            faster_whisper=FasterWhisperSettings(
                device=settings.asr.faster_whisper.device,
                model_size=settings.asr.faster_whisper.model_size,
                compute_type=settings.asr.faster_whisper.compute_type,
                transcription_mode=normalized_mode,
                models_dir=settings.asr.faster_whisper.models_dir,
            ),
        ),
        openai=settings.openai,
        workspace_ui=settings.workspace_ui,
        debug=settings.debug,
    )


def replace_openai_settings(
    settings: AppSettings,
    *,
    provider: str,
    base_url: str,
    model: str,
) -> AppSettings:
    return AppSettings(
        asr=settings.asr,
        openai=OpenAISettings(
            provider=provider,
            base_url=normalize_openai_base_url(base_url),
            model=model,
            api_key=settings.openai.api_key,
        ),
        workspace_ui=settings.workspace_ui,
        debug=settings.debug,
    )


def _normalize_theme(value: object) -> str:
    if isinstance(value, str) and value in VALID_THEMES:
        return value
    return "light"


def _normalize_transcription_mode(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_TRANSCRIPTION_MODES:
            return normalized
    return "fast"


def normalize_openai_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized[: -len("/chat/completions")]
    if normalized.endswith("/responses"):
        return normalized[: -len("/responses")]
    return normalized


def build_openai_responses_url(base_url: str) -> str:
    normalized = normalize_openai_base_url(base_url)
    return f"{normalized}/responses"


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
        f'transcription_mode = "{settings.asr.faster_whisper.transcription_mode}"',
        "",
        "[workspace_ui]",
        f'theme = "{settings.workspace_ui.theme}"',
        f"show_takeaways = {_toml_bool(settings.workspace_ui.show_takeaways)}",
        "",
        "[debug]",
        f"mode = {_toml_bool(settings.debug.mode)}",
        "",
    ]
    return "\n".join(lines)


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


@dataclass(frozen=True)
class EnvSettings:
    provider: str
    base_url: str
    model: str
    api_key: str


def load_env_settings(root_dir: Path) -> EnvSettings:
    values = _load_dotenv(root_dir / ".env")
    return EnvSettings(
        provider=values.get("OPENAI_PROVIDER", "openai_compatible").strip() or "openai_compatible",
        base_url=normalize_openai_base_url(values.get("OPENAI_BASE_URL", "").strip()),
        model=values.get("OPENAI_MODEL", "").strip(),
        api_key=values.get("OPENAI_API_KEY", "").strip(),
    )


def save_env_settings(root_dir: Path, settings: EnvSettings) -> None:
    dotenv_path = root_dir / ".env"
    lines = dotenv_path.read_text(encoding="utf-8").splitlines() if dotenv_path.exists() else []
    replacements = {
        "OPENAI_PROVIDER": settings.provider,
        "OPENAI_BASE_URL": normalize_openai_base_url(settings.base_url),
        "OPENAI_MODEL": settings.model,
        "OPENAI_API_KEY": settings.api_key,
    }
    next_lines: list[str] = []
    seen_keys: set[str] = set()

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            next_lines.append(raw_line)
            continue

        key, _ = raw_line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in replacements:
            next_lines.append(f"{normalized_key}={replacements[normalized_key]}")
            seen_keys.add(normalized_key)
        else:
            next_lines.append(raw_line)

    for key, value in replacements.items():
        if key not in seen_keys:
            next_lines.append(f"{key}={value}")

    dotenv_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def _load_dotenv(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip().strip('"').strip("'")
        if normalized_key:
            values[normalized_key] = normalized_value
    return values
