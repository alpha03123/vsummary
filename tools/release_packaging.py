from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"


@dataclass(frozen=True)
class HuggingFaceModelSpec:
    repo_id: str
    local_dir_name: str


@dataclass(frozen=True)
class PackageVariant:
    kind: str
    environment_file: Path
    settings_template: Path
    environment_name: str
    huggingface_models: tuple[HuggingFaceModelSpec, ...]


@dataclass(frozen=True)
class ReleaseLayout:
    pack_root: Path
    build_root: Path
    runtime_root: Path
    package_root: Path


PACKAGE_VARIANTS: dict[str, PackageVariant] = {
    "cpu": PackageVariant(
        kind="cpu",
        environment_file=Path("scripts/package/environment.cpu.yml"),
        settings_template=Path("scripts/package/settings.cpu.toml"),
        environment_name="vsummary-pack-cpu",
        huggingface_models=(
            HuggingFaceModelSpec(
                repo_id="BAAI/bge-base-zh-v1.5",
                local_dir_name="bge-base-zh-v1.5",
            ),
            HuggingFaceModelSpec(
                repo_id=RERANKER_MODEL_ID,
                local_dir_name="bge-reranker-v2-m3",
            ),
        ),
    ),
    "gpu": PackageVariant(
        kind="gpu",
        environment_file=Path("scripts/package/environment.gpu.yml"),
        settings_template=Path("scripts/package/settings.gpu.toml"),
        environment_name="vsummary-pack-gpu",
        huggingface_models=(
            HuggingFaceModelSpec(
                repo_id="BAAI/bge-base-zh-v1.5",
                local_dir_name="bge-base-zh-v1.5",
            ),
            HuggingFaceModelSpec(
                repo_id=RERANKER_MODEL_ID,
                local_dir_name="bge-reranker-v2-m3",
            ),
        ),
    ),
}


def build_release_layout(*, repo_root: Path, pack_root: Path, kind: str) -> ReleaseLayout:
    _ = repo_root
    normalized_pack_root = pack_root.resolve(strict=False)
    build_root = normalized_pack_root / "_build" / kind
    return ReleaseLayout(
        pack_root=normalized_pack_root,
        build_root=build_root,
        runtime_root=build_root / "runtime",
        package_root=normalized_pack_root / f"vsummary-{kind}",
    )


def collect_huggingface_model_ids(variant: PackageVariant) -> list[str]:
    return [model.repo_id for model in variant.huggingface_models]


def render_start_bat() -> str:
    return "\n".join(
        [
            "@echo off",
            "setlocal",
            "",
            'set "ROOT=%~dp0"',
            'if "%ROOT:~-1%"=="\\" set "ROOT=%ROOT:~0,-1%"',
            'cd /d "%ROOT%"',
            'if not exist "%ROOT%\\.env" copy /y "%ROOT%\\.env.example" "%ROOT%\\.env" >nul',
            'set "HF_HOME=%ROOT%\\data\\huggingface"',
            'set "HUGGINGFACE_HUB_CACHE=%ROOT%\\data\\huggingface\\hub"',
            'set "PATH=%ROOT%\\runtime;%ROOT%\\runtime\\Library\\bin;%ROOT%\\runtime\\Scripts;%PATH%"',
            'set "PYTHONPATH=%ROOT%\\src"',
            "",
            "start \"\" http://127.0.0.1:4173",
            'call "%ROOT%\\runtime\\python.exe" -m uvicorn backend.api.app:app --host 127.0.0.1 --port 4173',
            "if errorlevel 1 pause",
        ]
    )
