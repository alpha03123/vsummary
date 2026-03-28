from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


VALID_DEVICES = {"auto", "cpu", "gpu"}
VALID_ASR_PROVIDERS = {"whisper_cpp", "faster_whisper", "sensevoice"}


@dataclass(frozen=True)
class WhisperRuntimePaths:
    cpu_executable: Path
    gpu_executable: Path


@dataclass(frozen=True)
class WhisperCppSettings:
    device: str
    model_path: Path
    runtime_paths: WhisperRuntimePaths


@dataclass(frozen=True)
class FasterWhisperSettings:
    device: str
    model_size: str
    compute_type: str


@dataclass(frozen=True)
class SenseVoiceSettings:
    model_id: str
    device: str


@dataclass(frozen=True)
class AsrSettings:
    provider: str
    language: str
    whisper_cpp: WhisperCppSettings
    faster_whisper: FasterWhisperSettings
    sensevoice: SenseVoiceSettings


@dataclass(frozen=True)
class OpenAISettings:
    base_url: str
    model: str


@dataclass(frozen=True)
class AppSettings:
    asr: AsrSettings
    openai: OpenAISettings


def load_settings(config_path: Path, root_dir: Path) -> AppSettings:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    asr_payload = payload["asr"]
    provider = asr_payload["provider"].lower()
    if provider not in VALID_ASR_PROVIDERS:
        raise ValueError(f"Unsupported asr.provider: {provider}")

    whisper_payload = asr_payload["whisper_cpp"]
    whisper_device = whisper_payload["device"].lower()
    if whisper_device not in VALID_DEVICES:
        raise ValueError(f"Unsupported whisper_cpp.device: {whisper_device}")

    whisper_settings = WhisperCppSettings(
        device=whisper_device,
        model_path=_resolve(root_dir, whisper_payload["model_path"]),
        runtime_paths=WhisperRuntimePaths(
            cpu_executable=_resolve(root_dir, whisper_payload["runtime"]["cpu_executable"]),
            gpu_executable=_resolve(root_dir, whisper_payload["runtime"]["gpu_executable"]),
        ),
    )

    faster_payload = asr_payload["faster_whisper"]
    faster_device = faster_payload["device"].lower()
    if faster_device not in VALID_DEVICES:
        raise ValueError(f"Unsupported faster_whisper.device: {faster_device}")

    faster_settings = FasterWhisperSettings(
        device=faster_device,
        model_size=faster_payload["model_size"],
        compute_type=faster_payload["compute_type"],
    )

    sensevoice_payload = asr_payload["sensevoice"]
    sensevoice_settings = SenseVoiceSettings(
        model_id=sensevoice_payload["model_id"],
        device=sensevoice_payload["device"],
    )

    asr_settings = AsrSettings(
        provider=provider,
        language=asr_payload.get("language", "zh"),
        whisper_cpp=whisper_settings,
        faster_whisper=faster_settings,
        sensevoice=sensevoice_settings,
    )

    openai_payload = payload["openai"]
    openai_settings = OpenAISettings(
        base_url=openai_payload["base_url"],
        model=openai_payload["model"],
    )

    return AppSettings(asr=asr_settings, openai=openai_settings)


def _resolve(root_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return root_dir / path
